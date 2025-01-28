import schedule
import time
import pytz
import firebase_admin
from datetime import datetime, timedelta
from vesting_scripts.transfer_native_gcp import transfer_native_gcp
from vesting_scripts.transfer_token_gcp import transfer_token_gcp
from firebase_admin import firestore

# -------------------------------------------------
# UTILITY
# This script lets you implement a vesting schedule for assets custodied in Fordefi Vaults 
# Each asset config is stored in Firebase for easier management
# -------------------------------------------------

def load_vesting_configs():
    """
    This function fetches vesting configurations from a Firestore collection named 'vesting_configs'.
    
    Firestore DB Structure:
    ---------------------------------------
    Collection: vesting_configs
      Document ID: 652a2334-a673-4851-ad86-627781689592  <-- That's your Vault ID
        {
          "tokens": [
            {
              "asset": "BNB",
              "ecosystem": "evm",
              "type": "native",
              "chain": "bsc",
              "value": "0.000001",
              "note": "Daily BNB vesting",
              "cliff_days": 0,
              "vesting_time": "13:00",
              "destination": "0x..."
            },
            {
              "asset": "USDT",
              "ecosystem": "evm",
              "type": "erc20",
              "chain": "bsc",
              "value": "0.00001",
              "note": "Daily USDT vesting",
              "cliff_days": 0,
              "vesting_time": "19:00",
              "destination": "0x..."
            }
          ]
        }

    Returns a list of config dictionaries, where each config has:
      - vault_id
      - asset, ecosystem, type, chain, destination, value, note
      - cliff_days
      - vesting_time
    """
    db = firestore.client()
    configs = []

    # Retrieve all documents from the 'vesting_configs' collection on Firebase
    docs = db.collection("vesting_configs").stream()

    for doc in docs:
        doc_data = doc.to_dict()
        vault_id = doc.id
        tokens = doc_data.get("tokens", [])

        # Each doc can contain an array of tokens arrays
        for token_info in tokens:
            # NOTE -> decided against putting the smart contract address in that DB because 
            # the risk of mixing destination address and contract address are too great imo
            # The Vesting time should be expressed UTC time
            cfg = {
                "vault_id": vault_id,
                "asset":        token_info["asset"],
                "ecosystem":    token_info["ecosystem"],
                "type":         token_info["type"],
                "chain":        token_info["chain"],
                "destination":  token_info["destination"],
                "value":        token_info["value"],
                "note":         token_info["note"],
                "cliff_days":   token_info["cliff_days"], # This should be UTC time
                "vesting_time": token_info["vesting_time"]
            }
            configs.append(cfg)

    return configs


def execute_vest_for_asset(cfg: dict):
    """
    Execute a single vest for the given asset/config.
    """
    print(f"\n🔔 It's vesting time for {cfg['asset']} (Vault ID: {cfg['vault_id']})!")
    try:
        if cfg["type"] == "native" and cfg["ecosystem"] == "evm" and cfg["value"] != "0":
            # Send native EVM token (BNB, ETH, etc.)
            transfer_native_gcp(
                chain=cfg["chain"],
                vault_id=cfg["vault_id"],
                destination=cfg["destination"],
                value=cfg["value"],
                note=cfg["note"]
            )
        elif cfg["type"] == "erc20" and cfg["ecosystem"] == "evm" and cfg["value"] != "0":
            # Send ERC20 token (USDT, USDC, etc.)
            transfer_token_gcp(
                chain=cfg["chain"],
                token_ticker=cfg["asset"],
                vault_id=cfg["vault_id"],
                destination=cfg["destination"],
                amount=cfg["value"],
                note=cfg["note"]
            )
        elif cfg["value"] == "0":
            # If the vesting amount is zero, just inform
            print(f'❌ Vesting amount for {cfg["asset"]} in Firebase is 0!')
        else:
            raise ValueError(f"Unsupported configuration: type={cfg['type']}, ecosystem={cfg['ecosystem']}")

        print(f"✅ {cfg['asset']} vesting completed successfully.")
    except Exception as e:
        print(f"❌ Error during {cfg['asset']} vesting: {str(e)}")


def schedule_vesting_for_asset(cfg: dict, tag: str = "vesting"):
    """
    We take the vesting time (HH:MM) and cliff_days from cfg, and do the following:

    1) Compute the local day/time for the very first vest (including cliff_days).
    2) If that time is already in the past 'today', push it to tomorrow.
    3) Schedule that job to run daily at vest_hour:vest_minute (local system time).

    NOTE: 'schedule' library by default runs on the system's local time -> need to check with GCP
    """
    vest_hour, vest_minute = map(int, cfg["vesting_time"].split(":"))

    # Calculate 'cliff_days' offset from now (in UTC).
    now_utc = datetime.now(pytz.UTC)
    first_vest_date_utc = now_utc + timedelta(days=cfg["cliff_days"])

    # Convert from UTC to local server time zone
    local_tz = pytz.timezone("CET") 
    first_vest_local = first_vest_date_utc.astimezone(local_tz)

    # Applies the vest_hour:vest_minute
    first_vest_local = first_vest_local.replace(
        hour=vest_hour,
        minute=vest_minute,
        second=0,
        microsecond=0
    )

    # If we've passed that local time for the day, push to tomorrow
    now_local = datetime.now(local_tz)
    if first_vest_local <= now_local:
        first_vest_local += timedelta(days=1)

    # Format the HH:MM in local time for schedule.every().day.at("HH:MM")
    at_string = first_vest_local.strftime("%H:%M")

    # Small function that's calling the vest
    def daily_vest_job():
        execute_vest_for_asset(cfg)

    # Schedule the job every day at the local time "CET"
    schedule.every().day.at(at_string).do(daily_vest_job).tag(tag)

    print(f"⏰ {cfg['asset']} (Vault ID: {cfg['vault_id']}) first daily vest scheduled for {first_vest_local} local time.")


def refresh_vesting_schedules():
    """
    Clears out existing vesting jobs, reloads configs, and re-schedules them.
    We call this daily so that any new config entries are picked up.
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n--- Refreshing vesting schedules from Firestore at {current_time} ---")
    schedule.clear('vesting')

    configs = load_vesting_configs()
    print(f"Loaded {len(configs)} vesting configs.")

    for cfg in configs:
        schedule_vesting_for_asset(cfg, tag="vesting")


def main():
    # 1) Initialize Firebase
    firebase_admin.initialize_app()
    print("Firebase initialized successfully!")

    # 2) Initial refresh so we have tasks immediately
    refresh_vesting_schedules()

    # 3) Schedule a daily refresh at your_time UTC which is the local system time zone.
    schedule.every().day.at("13:00", "UTC").do(refresh_vesting_schedules)

    # 4) Keep the script alive
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()