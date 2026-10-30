from azure.identity import ClientSecretCredential
from azure.mgmt.resource.resources import ResourceManagementClient


def discover_azure_resources(tenant_id, client_id, client_secret, subscription_id):
    """Read resource metadata; usage and prices require separate collectors."""
    types = {
        "microsoft.compute/virtualmachines": "Virtual Machines",
        "microsoft.compute/disks": "Storage",
        "microsoft.storage/storageaccounts": "Storage",
        "microsoft.network/loadbalancers": "Load Balancers",
    }
    with ClientSecretCredential(
        tenant_id=tenant_id, client_id=client_id, client_secret=client_secret,
        connection_timeout=10, read_timeout=30, retry_total=1
    ) as credential:
        with ResourceManagementClient(
            credential, subscription_id,
            connection_timeout=10, read_timeout=30, retry_total=1
        ) as client:
            result = []
            for resource in client.resources.list():
                raw_type = resource.type or "Unknown"
                lowered = raw_type.lower()
                kind = types.get(lowered)
                if not kind:
                    if lowered.startswith("microsoft.network/"):
                        kind = "Networking"
                    elif lowered.startswith(("microsoft.sql/", "microsoft.dbformysql/", "microsoft.dbforpostgresql/")):
                        kind = "Databases"
                    else:
                        kind = raw_type
                result.append({
                    "id": resource.id, "resource_id": resource.id,
                    "name": resource.name, "provider": "Azure",
                    "type": kind, "azure_type": raw_type,
                    "region": resource.location, "status": "Not assessed",
                    "avg_cpu": None, "cost": None, "monthly_cost": None,
                    "savings": None, "potential_savings": None,
                    "recommendation": "Metrics have not been collected yet."
                })
            return result
