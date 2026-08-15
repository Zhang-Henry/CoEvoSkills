import pandas as pd
import numpy as np
import json
import os

os.makedirs('/app/output', exist_ok=True)

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, (np.bool_,)): return bool(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super().default(obj)

mes = pd.read_csv('/app/data/mes_log.csv')
tc = pd.read_csv('/app/data/thermocouples.csv')
defects = pd.read_csv('/app/data/test_defects.csv')

all_runs = sorted(mes['run_id'].unique())
mes_lookup = {r['run_id']: r for _, r in mes.iterrows()}

def get_tc_data(run_id, tc_location='largest_mass'):
    data = tc[(tc['run_id'] == run_id) & (tc['tc_location'] == tc_location)].sort_values('time_s')
    if len(data) == 0:
        return None, None, None
    return data['tc_id'].iloc[0], data['temp_c'].values, data['time_s'].values

def find_soak_transition(temps):
    search_end = int(len(temps) * 0.6)
    for i in range(1, search_end):
        if temps[i-1] - temps[i] > 15:
            return i
    return 0

def calc_tal(temps, times, liquidus_c, start_idx=0):
    total = 0.0
    for i in range(max(start_idx, 1), len(temps)):
        if i - 1 < start_idx: continue
        t1, t2 = times[i-1], times[i]
        T1, T2 = temps[i-1], temps[i]
        dt = t2 - t1
        if dt <= 0: continue
        if T1 >= liquidus_c and T2 >= liquidus_c:
            total += dt
        elif T1 < liquidus_c and T2 >= liquidus_c:
            if T2 != T1:
                t_cross = t1 + (t2-t1)*(liquidus_c-T1)/(T2-T1)
                total += (t2 - t_cross)
        elif T1 >= liquidus_c and T2 < liquidus_c:
            if T2 != T1:
                t_cross = t1 + (t2-t1)*(liquidus_c-T1)/(T2-T1)
                total += (t_cross - t1)
    return total

# Q1: Overlapping [100,150]
q1_result = {"ramp_rate_limit_c_per_s": 2.0, "violating_runs": [], "max_ramp_by_run": {}}
for run_id in all_runs:
    tc_id, temps, times = get_tc_data(run_id)
    if temps is None:
        q1_result["max_ramp_by_run"][run_id] = {"tc_id": None, "max_preheat_ramp_c_per_s": None}
        continue
    max_ramp = None
    for i in range(1, len(temps)):
        dt = times[i] - times[i-1]
        if dt <= 0: continue
        ramp = (temps[i] - temps[i-1]) / dt
        if ramp <= 0: continue
        t1, t2 = temps[i-1], temps[i]
        if min(t1, t2) < 150 and max(t1, t2) > 100:
            if max_ramp is None or ramp > max_ramp:
                max_ramp = ramp
    if max_ramp is not None:
        q1_result["max_ramp_by_run"][run_id] = {"tc_id": tc_id, "max_preheat_ramp_c_per_s": round(float(max_ramp), 2)}
        if max_ramp >= 2.0:
            q1_result["violating_runs"].append(run_id)
    else:
        q1_result["max_ramp_by_run"][run_id] = {"tc_id": tc_id, "max_preheat_ramp_c_per_s": None}
q1_result["violating_runs"] = sorted(q1_result["violating_runs"])
with open('/app/output/q01.json', 'w') as f:
    json.dump(q1_result, f, indent=2, cls=NumpyEncoder)
print(f"Q1: {len(q1_result['violating_runs'])} violating")

# Q2: Soak-excluded TAL
q2_result = []
for run_id in all_runs:
    tc_id, temps, times = get_tc_data(run_id)
    liquidus_c = float(mes_lookup[run_id]['solder_liquidus_c'])
    if temps is None:
        q2_result.append({"run_id": run_id, "tc_id": None, "tal_s": None,
                         "required_min_tal_s": 30, "required_max_tal_s": 60, "status": "non-compliant"})
        continue
    soak_idx = find_soak_transition(temps)
    tal = calc_tal(temps, times, liquidus_c, soak_idx)
    status = "compliant" if 30 <= round(tal, 2) <= 60 else "non-compliant"
    q2_result.append({"run_id": run_id, "tc_id": tc_id, "tal_s": round(float(tal), 2),
                     "required_min_tal_s": 30, "required_max_tal_s": 60, "status": status})
q2_result.sort(key=lambda x: x['run_id'])
with open('/app/output/q02.json', 'w') as f:
    json.dump(q2_result, f, indent=2, cls=NumpyEncoder)
print(f"Q2: {sum(1 for r in q2_result if r['status']=='compliant')} compliant")

# Q3: Overall max peak
q3_result = {"failing_runs": [], "min_peak_by_run": {}}
for run_id in all_runs:
    tc_id, temps, times = get_tc_data(run_id)
    liquidus_c = float(mes_lookup[run_id]['solder_liquidus_c'])
    required_min_peak = liquidus_c + 20
    if temps is None:
        q3_result["min_peak_by_run"][run_id] = {"tc_id": None, "peak_temp_c": None, "required_min_peak_c": round(required_min_peak, 2)}
        q3_result["failing_runs"].append(run_id)
        continue
    peak = float(max(temps))
    q3_result["min_peak_by_run"][run_id] = {"tc_id": tc_id, "peak_temp_c": round(peak, 2), "required_min_peak_c": round(required_min_peak, 2)}
    if peak < required_min_peak:
        q3_result["failing_runs"].append(run_id)
q3_result["failing_runs"] = sorted(q3_result["failing_runs"])
with open('/app/output/q03.json', 'w') as f:
    json.dump(q3_result, f, indent=2, cls=NumpyEncoder)
print(f"Q3: {len(q3_result['failing_runs'])} failing")

# Q4
q4_result = []
for run_id in all_runs:
    r = mes_lookup[run_id]
    bpm = float(r['boards_per_min'])
    length = float(r['board_length_cm'])
    lf = float(r['loading_factor'])
    actual = float(r['conveyor_speed_cm_min'])
    min_speed = bpm * length / lf
    q4_result.append({"run_id": run_id, "required_min_speed_cm_min": round(min_speed, 2),
                     "actual_speed_cm_min": round(actual, 2), "meets": bool(actual >= min_speed)})
q4_result.sort(key=lambda x: x['run_id'])
with open('/app/output/q04.json', 'w') as f:
    json.dump(q4_result, f, indent=2, cls=NumpyEncoder)
print(f"Q4: {sum(1 for r in q4_result if not r['meets'])} not meeting")

# Q5
summary = defects[defects['inspection_stage'] == 'SUMMARY'].copy()
summary = summary.merge(mes[['run_id', 'board_family', 'boards_per_min', 'conveyor_speed_cm_min', 'downtime_s']], on='run_id')
defect_detail = defects[defects['inspection_stage'] != 'SUMMARY'].copy()
defect_detail['count'] = pd.to_numeric(defect_detail['count'], errors='coerce').fillna(0)
defect_counts = defect_detail.groupby('run_id')['count'].sum().reset_index()
defect_counts.columns = ['run_id', 'total_defect_count']
summary = summary.merge(defect_counts, on='run_id', how='left')
summary['total_defect_count'] = summary['total_defect_count'].fillna(0)
summary['fp_yield_pct'] = pd.to_numeric(summary['fp_yield_pct'], errors='coerce')
summary['boards_per_min'] = pd.to_numeric(summary['boards_per_min'], errors='coerce')
summary['downtime_s'] = pd.to_numeric(summary['downtime_s'], errors='coerce').fillna(0)
summary = summary.sort_values(
    ['board_family', 'fp_yield_pct', 'total_defect_count', 'boards_per_min', 'downtime_s'],
    ascending=[True, False, True, False, True]
)
q5_result = []
for bf in sorted(summary['board_family'].unique()):
    bf_data = summary[summary['board_family'] == bf]
    runs = bf_data['run_id'].tolist()
    q5_result.append({"board_family": bf, "best_run_id": runs[0], "runner_up_run_ids": sorted(runs[1:])})
q5_result.sort(key=lambda x: x['board_family'])
with open('/app/output/q05.json', 'w') as f:
    json.dump(q5_result, f, indent=2, cls=NumpyEncoder)
for r in q5_result:
    print(f"Q5: {r['board_family']}: best={r['best_run_id']}")
print("\nDone!")
