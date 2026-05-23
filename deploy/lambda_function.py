"""
AWS Lambda Function — Model Instance Manager

Actions:
  • list     — List all model instances with status + IPs
  • start    — Start all model instances, wait for IPs, sync with Playground
  • stop     — Stop all model instances
  • sync     — Fetch current IPs and push to Playground
  • status   — Quick health check of all instances

Trigger: API Gateway (HTTP API) or direct invocation

Environment Variables:
  INSTANCE_IDS       — Comma-separated EC2 instance IDs
  PLAYGROUND_URL     — Playground base URL (e.g. http://3.6.251.189)
  REGION             — AWS region (default: ap-south-1)
"""

import json
import os
import time
import boto3
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Config ───────────────────────────────────────────────────────────────

INSTANCE_IDS = os.environ.get("INSTANCE_IDS", "").split(",")
PLAYGROUND_URL = os.environ.get("PLAYGROUND_URL", "http://3.6.251.189")
REGION = os.environ.get("REGION", "ap-south-1")

ec2 = boto3.client("ec2", region_name=REGION)


def lambda_handler(event, context):
    """Main Lambda entry point."""

    # Support API Gateway (HTTP API) and direct invocation
    if "body" in event:
        try:
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        except (json.JSONDecodeError, TypeError):
            body = {}
        action = event.get("queryStringParameters", {}).get("action", "list")
    else:
        body = event
        action = event.get("action", "list")

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
    """Format API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }


# ── Actions ──────────────────────────────────────────────────────────────

def action_list(body):
    """List all model instances with their state and IPs."""
    ids = _get_instance_ids(body)
    if not ids:
        return {"error": "No instance IDs configured"}

    reservations = ec2.describe_instances(InstanceIds=ids)["Reservations"]
    instances = []
    for res in reservations:
        for inst in res["Instances"]:
            name_tag = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), "unnamed")
            instances.append({
                "instance_id": inst["InstanceId"],
                "name": name_tag,
                "state": inst["State"]["Name"],
                "public_ip": inst.get("PublicIpAddress"),
                "private_ip": inst.get("PrivateIpAddress"),
                "instance_type": inst["InstanceType"],
            })

    return {"instances": instances, "count": len(instances)}


def action_start(body):
    """Start all model instances, wait for IPs, then sync with Playground."""
    ids = _get_instance_ids(body)
    if not ids:
        return {"error": "No instance IDs configured"}

    # Start instances
    ec2.start_instances(InstanceIds=ids)
    print(f"Starting instances: {ids}")

    # Wait for running state (max 120s)
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(
        InstanceIds=ids,
        WaiterConfig={"Delay": 5, "MaxAttempts": 24}
    )
    print("All instances running")

    # Small delay for Public IP assignment
    time.sleep(5)

    # Fetch IPs and sync
    return action_sync(body)


def action_stop(body):
    """Stop all model instances."""
    ids = _get_instance_ids(body)
    if not ids:
        return {"error": "No instance IDs configured"}

    ec2.stop_instances(InstanceIds=ids)
    return {"status": "stopping", "instances": ids}


def action_sync(body):
    """Fetch current Public IPs and push them to the Playground."""
    ids = _get_instance_ids(body)
    if not ids:
        return {"error": "No instance IDs configured"}

    reservations = ec2.describe_instances(InstanceIds=ids)["Reservations"]

    # Build instance_id → public_ip mapping
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

    # Push to Playground
    playground_url = body.get("playground_url", PLAYGROUND_URL).rstrip("/")
    sync_url = f"{playground_url}/api/admin/sync-ips"

    try:
        data = json.dumps({"updates": updates}).encode()
        req = Request(sync_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=10) as resp:
            sync_result = json.loads(resp.read())
    except URLError as e:
        sync_result = {"error": f"Could not reach Playground at {sync_url}: {str(e)}"}

    return {
        "status": "synced",
        "instances": details,
        "sync_result": sync_result,
    }


def action_status(body):
    """Quick status check — is each instance running?"""
    ids = _get_instance_ids(body)
    if not ids:
        return {"error": "No instance IDs configured"}

    reservations = ec2.describe_instances(InstanceIds=ids)["Reservations"]
    states = {}
    for res in reservations:
        for inst in res["Instances"]:
            name = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), inst["InstanceId"])
            states[name] = {
                "state": inst["State"]["Name"],
                "ip": inst.get("PublicIpAddress"),
            }

    all_running = all(s["state"] == "running" for s in states.values())
    return {"all_running": all_running, "instances": states}


# ── Helpers ──────────────────────────────────────────────────────────────

def _get_instance_ids(body):
    """Get instance IDs from request body or environment."""
    ids = body.get("instance_ids", [])
    if not ids:
        ids = [x.strip() for x in INSTANCE_IDS if x.strip()]
    return ids
