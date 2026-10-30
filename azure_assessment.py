from datetime import datetime, timedelta, timezone
from contextlib import ExitStack

from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.core.exceptions import AzureError

from azure_connector import discover_azure_resources
from assessment import assess, summarize


def prop(obj, name, default=None):
    """Support both flattened and nested Azure SDK resource models."""
    value = getattr(obj, name, None)
    if value is None:
        value = getattr(getattr(obj, 'properties', None), name, None)
    return default if value is None else value


def assess_azure(tenant_id, client_id, client_secret, subscription_id):
    inventory = discover_azure_resources(tenant_id, client_id, client_secret, subscription_id)
    warnings = []
    if not inventory:
        return payload([], 'live', warnings)
    settings = dict(connection_timeout=10, read_timeout=30, retry_total=1)
    with ExitStack() as stack:
        credential = stack.enter_context(ClientSecretCredential(tenant_id, client_id, client_secret, **settings))
        compute = stack.enter_context(ComputeManagementClient(credential, subscription_id, **settings))
        network = stack.enter_context(NetworkManagementClient(credential, subscription_id, **settings))
        monitor = stack.enter_context(MonitorManagementClient(credential, subscription_id, **settings))
        disks, ips = {}, {}
        kinds = {r['azure_type'].lower() for r in inventory}
        if 'microsoft.compute/disks' in kinds:
            try:
                disks = {d.id.lower(): d for d in compute.disks.list()}
            except AzureError:
                warnings.append('Disk details unavailable; affected disks remain unassessed.')
        if 'microsoft.network/publicipaddresses' in kinds:
            try:
                ips = {p.id.lower(): p for p in network.public_ip_addresses.list_all()}
            except AzureError:
                warnings.append('Public IP details unavailable; affected addresses remain unassessed.')
        end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=7)
        timespan = f'{start.isoformat()}/{end.isoformat()}'
        vm_count = 0
        results = []
        for source in inventory:
            r = dict(source, peak_cpu=None, cpu_coverage=None, cpu_samples_count=0)
            key = r['id'].lower()
            kind = r['azure_type'].lower()
            if kind == 'microsoft.compute/disks' and key in disks:
                d = disks[key]
                state = prop(d, 'disk_state')
                r['disk_state'] = getattr(state, 'value', state)
                r['attached'] = bool(prop(d, 'managed_by') or prop(d, 'managed_by_extended'))
            elif kind == 'microsoft.network/publicipaddresses' and key in ips:
                p = ips[key]
                state = prop(p, 'provisioning_state')
                r['association_checked'] = getattr(state, 'value', state) == 'Succeeded'
                r['associated'] = any(prop(p, field) is not None for field in (
                    'ip_configuration', 'nat_gateway', 'linked_public_ip_address', 'service_public_ip_address'
                ))
            elif kind == 'microsoft.compute/virtualmachines':
                vm_count += 1
                if vm_count > 20:
                    warnings.append('Prototype limit: CPU assessed for only the first 20 VMs.')
                else:
                    try:
                        metrics = monitor.metrics.list(
                            resource_uri=r['id'], timespan=timespan, interval='PT1H',
                            metricnames='Percentage CPU', aggregation='Average,Maximum'
                        )
                        hourly = {}
                        for metric in metrics.value or []:
                            for series in metric.timeseries or []:
                                for point in series.data or []:
                                    stamp = point.time_stamp
                                    if stamp is not None and stamp.tzinfo is None:
                                        stamp = stamp.replace(tzinfo=timezone.utc)
                                    if stamp is not None and start <= stamp < end and point.average is not None:
                                        hourly[stamp] = (point.average, point.maximum)
                        r['cpu_samples'] = [v[0] for v in hourly.values()]
                        peaks = [v[1] for v in hourly.values() if v[1] is not None]
                        r['peak_cpu'] = max(peaks) if len(peaks) == len(hourly) and peaks else None
                    except AzureError:
                        warnings.append('CPU metrics unavailable for one or more VMs; no idle finding is inferred for them.')
            results.append(assess(r))
    return payload(results, 'live', list(dict.fromkeys(warnings)))


def payload(resources, mode, warnings=None):
    distribution = {}
    for r in resources:
        distribution[r['type']] = distribution.get(r['type'], 0) + 1
    return dict(mode=mode, source='Synthetic demonstration' if mode == 'demo' else 'Live Azure',
                generated_at=datetime.now(timezone.utc).isoformat(), warnings=warnings or [],
                summary=summarize(resources), distribution=distribution, resources=resources)
