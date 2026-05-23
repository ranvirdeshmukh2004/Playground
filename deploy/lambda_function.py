"""
AWS Lambda Function — Model Instance Manager

Actions:
  • list     — List all instances (5 total) with status + IPs
  • start    — Start Playground + 4 model instances, wait, sync IPs
  • stop     — Stop all 5 instances
  • status   — Quick health check

Trigger: API Gateway (HTTP API) or direct invocation

Environment Variables:
  MODEL_INSTANCE_IDS      — Comma-separated model EC2 instance IDs (4 models)
  PLAYGROUND_INSTANCE_ID  — Playground EC2 instance ID (has Elastic IP)
  PLAYGROUND_URL          — Playground URL (e.g. http://3.6.251.189)
  REGION                  — AWS region (default: ap-south-1)
"""

import json
import os
import time
import boto3
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Config ───────────────────────────────────────────────────────────────

MODEL_INSTANCE_IDS = [x.strip() for x in os.environ.get("MODEL_INSTANCE_IDS", "").split(",") if x.strip()]
PLAYGROUND_INSTANCE_ID = os.environ.get("PLAYGROUND_INSTANCE_ID", "").strip()
PLAYGROUND_URL = os.environ.get("PLAYGROUND_URL", "http://3.6.251.189")
REGION = os.environ.get("REGION", "ap-south-1")

ec2 = boto3.client("ec2", region_name=REGION)


def _all_instance_ids():
    """All 5 instance IDs (playground + 4 models)."""
    ids = list(MODEL_INSTANCE_IDS)
    if PLAYGROUND_INSTANCE_ID:
        ids.append(PLAYGROUND_INSTANCE_ID)
    return ids


def lambda_handler(event, context):
    """Main Lambda entry point."""

    # Parse action from query string, body, or event
    query_params = event.get("queryStringParameters") or {}
    body_raw = event.get("body")

    if body_raw and isinstance(body_raw, str):
        try:
            body = json.loads(body_raw)
        except (json.JSONDecodeError, TypeError):
            body = {}
    elif isinstance(body_raw, dict):
        body = body_raw
    elif not body_raw and "action" in event:
        body = event
    else:
        body = {}

    action = query_params.get("action") or body.get("action", "list")

    actions = {
        "list": action_list,
        "start": action_start,
        "stop": action_stop,
        "sync": action_sync,
        "status": action_status,
    }

    handler = actions.get(action)
    if not handler:
        return response(400, {"error": f"Unknown action: {action}. Use: {list(actions.keys())}"})

    try:
        result = handler(body)
        return response(200, result)
    except Exception as e:
        return response(500, {"error": str(e)})


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, default=str),
    }


# ── Actions ──────────────────────────────────────────────────────────────

def action_list(body):
    """List ALL 5 instances with state and IPs."""
    ids = _all_instance_ids()
    if not ids:
        return {"error": "No instance IDs configured"}

    reservations = ec2.describe_instances(InstanceIds=ids)["Reservations"]
    instances = []
    for res in reservations:
        for inst in res["Instances"]:
            iid = inst["InstanceId"]
            name = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), "unnamed")
            is_playground = (iid == PLAYGROUND_INSTANCE_ID)
            instances.append({
                "instance_id": iid,
                "name": name,
                "role": "playground" if is_playground else "model",
                "state": inst["State"]["Name"],
                "public_ip": inst.get("PublicIpAddress"),
                "private_ip": inst.get("PrivateIpAddress"),
                "instance_type": inst["InstanceType"],
                "elastic_ip": is_playground,
            })

    return {"instances": instances, "count": len(instances)}


def action_start(body):
    """Start all 5 instances → wait → sync model IPs to Playground."""
    all_ids = _all_instance_ids()
    if not all_ids:
        return {"error": "No instance IDs configured"}

    # Step 1: Start ALL instances (playground + models)
    ec2.start_instances(InstanceIds=all_ids)
    print(f"[START] Starting {len(all_ids)} instances: {all_ids}")

    # Step 2: Wait for all to be running
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=all_ids, WaiterConfig={"Delay": 5, "MaxAttempts": 30})
    print("[START] All instances running")

    # Step 3: Wait for Playground FastAPI to boot (Supervisor/PM2 auto-starts it)
    print("[START] Waiting 20s for Playground server to boot...")
    time.sleep(20)

    # Step 4: Sync model IPs to Playground
    sync_result = _sync_model_ips()

    # Step 5: Get final state of all instances
    reservations = ec2.describe_instances(InstanceIds=all_ids)["Reservations"]
    instances = []
    for res in reservations:
        for inst in res["Instances"]:
            iid = inst["InstanceId"]
            name = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), "unnamed")
            instances.append({
                "instance_id": iid,
                "name": name,
                "role": "playground" if iid == PLAYGROUND_INSTANCE_ID else "model",
                "state": inst["State"]["Name"],
                "public_ip": inst.get("PublicIpAddress"),
            })

    return {
        "status": "started",
        "message": f"All {len(all_ids)} instances started. Model IPs synced to Playground.",
        "instances": instances,
        "sync_result": sync_result,
    }


def action_stop(body):
    """Stop ALL 5 instances."""
    all_ids = _all_instance_ids()
    if not all_ids:
        return {"error": "No instance IDs configured"}

    ec2.stop_instances(InstanceIds=all_ids)

    return {
        "status": "stopping",
        "message": f"Stopping {len(all_ids)} instances (4 models + playground).",
        "instances": all_ids,
    }


def action_sync(body):
    """Fetch model Public IPs and push to Playground."""
    return _sync_model_ips()


def action_status(body):
    """Quick status check of all 5 instances."""
    all_ids = _all_instance_ids()
    if not all_ids:
        return {"error": "No instance IDs configured"}

    reservations = ec2.describe_instances(InstanceIds=all_ids)["Reservations"]
    instances = {}
    for res in reservations:
        for inst in res["Instances"]:
            iid = inst["InstanceId"]
            name = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), iid)
            instances[name] = {
                "state": inst["State"]["Name"],
                "ip": inst.get("PublicIpAddress"),
                "role": "playground" if iid == PLAYGROUND_INSTANCE_ID else "model",
            }

    all_running = all(s["state"] == "running" for s in instances.values())
    return {
        "all_running": all_running,
        "total": len(instances),
        "instances": instances,
    }


# ── Internal helpers ─────────────────────────────────────────────────────

def _sync_model_ips():
    """Fetch model instance IPs and push them to the Playground."""
    if not MODEL_INSTANCE_IDS:
        return {"error": "No model instance IDs configured"}

    reservations = ec2.describe_instances(InstanceIds=MODEL_INSTANCE_IDS)["Reservations"]

    updates = {}
    details = []
    for res in reservations:
        for inst in res["Instances"]:
            iid = inst["InstanceId"]
            ip = inst.get("PublicIpAddress")
            state = inst["State"]["Name"]
            name = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), "unnamed")
            updates[iid] = ip
            details.append({
                "instance_id": iid,
                "name": name,
                "state": state,
                "public_ip": ip,
            })

    # Push to Playground (Elastic IP — always reachable)
    playground_url = PLAYGROUND_URL.rstrip("/")
    sync_url = f"{playground_url}/api/admin/sync-ips"

    try:
        data = json.dumps({"updates": updates}).encode()
        req = Request(sync_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=15) as resp:
            sync_result = json.loads(resp.read())
    except URLError as e:
        sync_result = {"error": f"Could not reach Playground at {sync_url}: {str(e)}"}

    return {
        "status": "synced",
        "models_synced": len([d for d in details if d["public_ip"]]),
        "models": details,
        "playground_response": sync_result,
    }
