import argparse
import os
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv
from cognite.client import CogniteClient
from cognite.client.config import ClientConfig
from cognite.client.credentials import OAuthClientCredentials  # replaces non-existent CredentialProvider
from cognite.client.data_classes.data_modeling import NodeId   # moved to data_modeling in SDK >= v7
from cognite.client.exceptions import CogniteNotFoundError

# Project root is one level above admin/ — that is where .env and config.dev.yaml live
ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
CONFIG_PATH = ROOT_DIR / "config.dev.yaml"
load_dotenv(dotenv_path=ENV_PATH)

# --- CONFIGURATION FROM YOUR COGNITE-TOOLKIT .env ---
CLIENT_ID = os.getenv("IDP_CLIENT_ID")
CLIENT_SECRET = os.getenv("IDP_CLIENT_SECRET")
TOKEN_URL = os.getenv("IDP_TOKEN_URL")
AUDIENCE = os.getenv("IDP_AUDIENCE", "https://cognitedata.com")
SCOPES = os.getenv("IDP_SCOPES", "user_impersonation")

CDF_CLUSTER = os.getenv("CDF_CLUSTER", "westeurope-1")
PROJECT = os.getenv("CDF_PROJECT", "ptec-04")
# Load userPrefix and instanceSpace from the CDF Toolkit config — same values
# used by `cdf deploy`, so they stay in sync automatically.
def _load_module_config() -> tuple[str, str]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    node = cfg["variables"]["modules"]["custom"]["cookie_manufacturing"]
    return node["userPrefix"], node["isaInstanceSpace"]

USER_PREFIX, INSTANCE_SPACE = _load_module_config()

# Local source file configuration
CSV_PATH = ROOT_DIR / "data" / "resources" / "datapoints" / "timeseries_datapoints.csv"

def get_cognite_client() -> CogniteClient:
    """Initializes the CogniteClient using Auth0 OAuth2 client-credentials flow."""
    if not all([CLIENT_ID, CLIENT_SECRET, TOKEN_URL]):
        raise RuntimeError(
            "Missing required Auth0 variables (IDP_CLIENT_ID, IDP_CLIENT_SECRET, "
            "IDP_TOKEN_URL) in .env"
        )

    token_scopes = SCOPES.replace(",", " ").split()

    # The datamosaix-prod Auth0 tenant works without an explicit audience —
    # same behaviour as the tested REST script.  Audience is only forwarded
    # when IDP_AUDIENCE is explicitly set in the environment to a non-default value.
    token_extra: dict = {}
    if AUDIENCE and AUDIENCE != "https://cognitedata.com":
        token_extra["audience"] = AUDIENCE

    credentials = OAuthClientCredentials(
        token_url=TOKEN_URL,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=token_scopes,
        **({"token_custom_args": token_extra} if token_extra else {}),
    )
    config = ClientConfig(
        client_name="toolkit-datapoints-uploader",
        project=PROJECT,
        credentials=credentials,
        base_url=f"https://{CDF_CLUSTER}.cognitedata.com",
    )
    return CogniteClient(config)

def load_and_parse_csv(path: Path) -> pd.DataFrame:
    """Loads a wide-format CSV file and converts timestamps to epoch ms."""
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found at: {path}")
        
    df = pd.read_csv(path, parse_dates=["timestamp"])
    # Convert pandas timestamp to UNIX epoch milliseconds
    df["timestamp"] = df["timestamp"].astype("int64") // 10**6
    return df

def main():
    parser = argparse.ArgumentParser(
        description="Upload ISA TimeSeries datapoints to CDF using the cognite-sdk."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and count datapoints without writing anything to CDF.",
    )
    args = parser.parse_args()

    client = get_cognite_client()

    print(f"USER_PREFIX   : {USER_PREFIX}")
    print(f"INSTANCE_SPACE: {INSTANCE_SPACE}")
    print(f"Loading CSV   : {CSV_PATH}")
    df = load_and_parse_csv(CSV_PATH)

    ts_columns = [col for col in df.columns if col != "timestamp"]
    print(f"Found {len(ts_columns)} time series columns to process.")

    fdm_payload     = []  # instanceId  → FDM ISATimeSeries nodes
    classic_payload = []  # externalId  → classic CDF TimeSeries

    for col in ts_columns:
        valid_rows = df[["timestamp", col]].dropna()
        if valid_rows.empty:
            continue

        # Convert numpy int64 → Python int for SDK compatibility
        datapoints = [
            (int(ts), float(val))
            for ts, val in zip(valid_rows["timestamp"], valid_rows[col])
        ]

        # Prepend the deployment prefix so the external ID matches what is in CDF
        # (CSV columns are stored without it)
        ext_id = col if col.startswith(USER_PREFIX) else f"{USER_PREFIX}{col}"

        fdm_payload.append({
            "instanceId": NodeId(space=INSTANCE_SPACE, external_id=ext_id),
            "datapoints": datapoints,
        })
        classic_payload.append({
            "externalId": ext_id,
            "datapoints": datapoints,
        })

    if not fdm_payload:
        print("No valid data points found to push.")
        return

    total_points = sum(len(item["datapoints"]) for item in fdm_payload)
    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"Mode          : {mode}")
    print(f"Timeseries    : {len(fdm_payload)}")
    print(f"Total points  : {total_points:,}")

    if args.dry_run:
        print("Dry run complete — no data written to CDF.")
        return

    # ── 1. FDM ISATimeSeries (instanceId) ────────────────────────────────────
    try:
        client.time_series.data.insert_multiple(fdm_payload)
        print(f"[OK] FDM upload complete   — {len(fdm_payload)} ISATimeSeries nodes written.")
    except CogniteNotFoundError as e:
        print("\n[WARN] FDM upload — one or more ISATimeSeries nodes not found in CDF.")
        print("Tip: run `cdf deploy` and the workflow to ensure ISATimeSeries instances exist.")
        print(f"Details: {e}")
    except Exception as e:
        print(f"\n[ERROR] FDM upload failed: {e}")

    # ── 2. Classic CDF TimeSeries (externalId) ────────────────────────────────
    try:
        client.time_series.data.insert_multiple(classic_payload)
        print(f"[OK] Classic upload complete — {len(classic_payload)} classic TimeSeries written.")
    except CogniteNotFoundError as e:
        print("\n[WARN] Classic upload — one or more classic TimeSeries not found in CDF.")
        print("Tip: run `cdf deploy` first to ensure all TimeSeries resources exist.")
        print(f"Details: {e}")
    except Exception as e:
        print(f"\n[ERROR] Classic upload failed: {e}")

if __name__ == "__main__":
    main()