"""ACC Simulation runner - position-based distance tracking."""
import sys, csv, yaml, os
scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, scripts_dir)
from acc_system import AdaptiveCruiseControl

def load_sensor_data(filepath):
    data = []
    with open(filepath, 'r') as f:
        for row in csv.DictReader(f):
            data.append({
                'time': float(row['time']),
                'ego_speed': float(row['ego_speed']),
                'lead_speed': float(row['lead_speed']) if row['lead_speed'].strip() else None,
                'distance': float(row['distance']) if row['distance'].strip() else None,
            })
    return data

def run_simulation(vp, tr, sd, out):
    with open(vp) as f: vc = yaml.safe_load(f)
    with open(tr) as f: tu = yaml.safe_load(f)
    cfg = dict(vc)
    cfg['pid_speed'] = tu['pid_speed']
    cfg['pid_distance'] = tu['pid_distance']
    sdata = load_sensor_data(sd)
    acc = AdaptiveCruiseControl(cfg)
    dt = cfg['simulation']['dt']
    
    ego_speed = 0.0
    ego_pos = 0.0
    lead_pos = None
    lead_on = False
    results = []
    
    for s in sdata:
        ls, sdist = s['lead_speed'], s['distance']
        has_lead = ls is not None and sdist is not None
        
        if has_lead:
            if not lead_on:
                lead_pos = ego_pos + sdist
                lead_on = True
            dist = lead_pos - ego_pos
            if dist < 0.01: dist = 0.01
        else:
            dist = None
            lead_pos = None
            lead_on = False
        
        accel, mode, derr = acc.compute(
            ego_speed, ls if has_lead else None, dist if has_lead else None, dt)
        
        ttc = None
        if has_lead and dist and ego_speed > ls and dist > 0:
            ttc = dist / (ego_speed - ls)
        
        results.append({
            'time': round(s['time'], 1),
            'ego_speed': round(ego_speed, 4),
            'acceleration_cmd': round(accel, 4),
            'mode': mode,
            'distance_error': round(derr, 4) if derr is not None else '',
            'distance': round(dist, 4) if dist is not None else '',
            'ttc': round(ttc, 4) if ttc is not None else '',
        })
        
        # CORRECT ORDER: update positions FIRST (using current speeds)
        # then update speeds
        ego_pos += ego_speed * dt  # x(t+dt) = x(t) + v(t)*dt
        if has_lead and lead_pos is not None:
            lead_pos += ls * dt  # lead position update
        
        # Now update ego speed
        ego_speed += accel * dt  # v(t+dt) = v(t) + a(t)*dt
        if ego_speed < 0: ego_speed = 0.0
    
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['time','ego_speed','acceleration_cmd','mode','distance_error','distance','ttc'])
        w.writeheader()
        w.writerows(results)
    return results

def analyze(results):
    rt = next((r['time'] for r in results if r['ego_speed'] >= 27), None)
    mx = max(r['ego_speed'] for r in results)
    cf = [r for r in results if r['time'] >= 140 and r['mode'] == 'cruise']
    af = sum(r['ego_speed'] for r in cf)/len(cf) if cf else 0
    fw = [r for r in results if r['mode'] in ('follow','emergency')]
    l20 = fw[int(len(fw)*0.8):]
    errs = [abs(float(r['distance_error'])) for r in l20 if r['distance_error'] != '']
    ade = sum(errs)/len(errs) if errs else 999
    dr = [r for r in results if r['distance'] != '']
    md = min(float(r['distance']) for r in dr) if dr else 999
    ci = [r for r in results if 25 <= r['time'] <= 29 and r['mode'] == 'cruise']
    aci = sum(r['ego_speed'] for r in ci)/len(ci) if ci else 0
    print(f"Rise: {rt}s | Max: {mx:.2f} ({(mx-30)/30*100:.1f}%)")
    print(f"Cruise init: {aci:.2f} | Final: {af:.2f} (err {abs(af-30):.3f})")
    print(f"Min dist: {md:.2f} | Avg |dist_err| late: {ade:.2f}")
    for i in range(0, len(l20), 40):
        r = l20[i]
        print(f"  t={r['time']} ego={r['ego_speed']:.1f} dist={float(r['distance']) if r['distance'] else 0:.1f} derr={float(r['distance_error']) if r['distance_error'] else 0:.1f}")

if __name__ == '__main__':
    bd = '/root'
    r = run_simulation(f'{bd}/vehicle_params.yaml', f'{bd}/tuning_results.yaml',
                       f'{bd}/sensor_data.csv', f'{bd}/simulation_results.csv')
    print('Done.'); analyze(r)
