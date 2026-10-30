"""Conservative review rules. Findings never execute Azure changes."""
import math


def assess(resource):
    r = dict(resource)
    r.update(status='Not assessed', recommendation=None, finding=False)
    kind = r.get('azure_type', '').lower()
    if kind == 'microsoft.compute/disks':
        if r.get('disk_state') == 'Unattached' and not r.get('attached'):
            r.update(status='Unattached', finding=True,
                     recommendation='Review ownership and backup requirements; delete manually only if no longer needed.')
        elif r.get('attached'):
            r['status'] = 'Attached'
    elif kind == 'microsoft.network/publicipaddresses':
        if r.get('association_checked'):
            if r.get('associated'):
                r['status'] = 'Associated'
            else:
                r.update(status='Unassociated', finding=True,
                         recommendation='Review planned use and dependencies; release manually if unnecessary.')
    elif kind == 'microsoft.compute/virtualmachines':
        points = r.get('cpu_samples', [])
        valid = [p for p in points if isinstance(p, (int, float)) and math.isfinite(p) and 0 <= p <= 100]
        r['cpu_samples_count'] = len(valid)
        r['avg_cpu'] = round(sum(valid) / len(valid), 2) if valid else None
        r['cpu_coverage'] = round(min(len(valid) / 168, 1) * 100, 1)
        if len(valid) < 135:  # At least 80% of a seven-day hourly window.
            r['status'] = 'Insufficient data'
        else:
            average = sum(valid) / len(valid)
            peak = r.get('peak_cpu')
            if average < 1 and peak is not None and peak < 10:
                r.update(status='Idle candidate', finding=True,
                         recommendation='Low CPU over seven days. Check memory, disk, network and scheduled jobs before stopping.')
            elif average < 10 and peak is not None and peak < 50:
                r.update(status='Underutilized candidate', finding=True,
                         recommendation='Review a smaller VM size after checking memory, I/O and peak workload requirements.')
            else:
                r['status'] = 'No CPU finding'
    r.pop('cpu_samples', None)
    # Live prices are unknown; synthetic demo prices are explicitly supplied.
    cost = r.get('cost')
    if r['finding'] and isinstance(cost, (int, float)):
        factor = .5 if r['status'] == 'Underutilized candidate' else 1
        r['savings'] = round(cost * factor, 2)
    else:
        r['savings'] = 0 if cost is not None else None
    return r


def summarize(resources):
    assessed = [r for r in resources if r['status'] not in ('Not assessed', 'Insufficient data')]
    known_costs = [r['cost'] for r in resources if r.get('cost') is not None]
    known_savings = [r['savings'] for r in resources if r.get('savings') is not None]
    return {
        'total_resources': len(resources),
        'assessed_resources': len(assessed),
        'idle_resources': sum(r['status'] in ('Idle candidate', 'Unattached', 'Unassociated') for r in resources),
        'findings': sum(bool(r['finding']) for r in resources),
        'monthly_cost': round(sum(known_costs), 2) if resources and len(known_costs) == len(resources) else None,
        'potential_savings': round(sum(known_savings), 2) if resources and len(known_savings) == len(resources) else None,
        'optimization_score': None,
    }


def demo_resources():
    """Synthetic inputs run through exactly the same rules as live inputs."""
    def row(name, kind, cost, **extra):
        return dict(id='demo/' + name, name=name, provider='Azure (demo)',
                    type=kind, azure_type={'VM':'Microsoft.Compute/virtualMachines',
                    'Disk':'Microsoft.Compute/disks', 'Public IP':'Microsoft.Network/publicIPAddresses'}[kind],
                    region='eastus (demo)', cost=cost, avg_cpu=None, peak_cpu=None,
                    cpu_coverage=None, cpu_samples_count=0, **extra)
    return [assess(r) for r in [
        row('demo-api-vm', 'VM', 120, cpu_samples=[42] * 168),
        dict(row('demo-idle-vm', 'VM', 80, cpu_samples=[.3] * 168), peak_cpu=2),
        dict(row('demo-oversized-vm', 'VM', 160, cpu_samples=[5] * 168), peak_cpu=20),
        row('demo-new-vm', 'VM', 40, cpu_samples=[0] * 8),
        row('demo-unused-disk', 'Disk', 20, disk_state='Unattached', attached=False),
        row('demo-data-disk', 'Disk', 30, disk_state='Attached', attached=True),
        row('demo-unused-ip', 'Public IP', 4, association_checked=True, associated=False),
    ]]
