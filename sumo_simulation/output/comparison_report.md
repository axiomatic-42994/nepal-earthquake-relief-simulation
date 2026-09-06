# Simulation Performance Comparison: Dynamic TraCI Rerouting vs. Static Baseline

## 1. Overall System Performance Summary

| Metric | Static Baseline (No Rerouting) | Dynamic TraCI Rerouting | Improvement / Delta |
|---|:---:|:---:|:---:|
| **Total Dispatched Vehicles** | 150 | 150 | - |
| **Successfully Completed Trips** | 128 (85.3%) | 145 (96.7%) | **+17 vehicles delivered** |
| **Stranded / Jammed Vehicles** | 22 | 5 | **-17 stuck vehicles** |
| **Mission Fulfillment Rate ($\le 300\text{s}$)** | 68.7% | 94.7% | **+26.0% gain** |
| **Average Delivery Duration** | 248.0 s (4.1 min) | 161.6 s (2.7 min) | **34.8% faster (86.4s saved)** |
| **Average Stopped Waiting Time** | 94.3 s | 6.6 s | **93.0% queue reduction** |
| **Average Route Distance** | 2.34 km | 2.31 km | +-29 m (detour margin) |

---

## 2. Performance Breakdown by Relief Vehicle Category

### A. Ambulances
- **Static Baseline:** Completed: 83 | Avg Duration: 241.6s | Avg Waiting: 95.6s
- **Dynamic Rerouting:** Completed: 94 | Avg Duration: 154.2s | Avg Waiting: 5.0s
- **Key Takeaway:** Ambulances in dynamic mode avoid central corridor gridlocks, saving **90.6 seconds of stopped delay**.

### B. First Responders
- **Static Baseline:** Completed: 25 | Avg Duration: 248.0s | Avg Waiting: 82.7s
- **Dynamic Rerouting:** Completed: 27 | Avg Duration: 163.8s | Avg Waiting: 1.3s
- **Key Takeaway:** First responder units achieved a **84.2s duration improvement**, crucial for time-sensitive search and rescue ops.

### C. Heavy Cargo Trucks
- **Static Baseline:** Completed: 20 | Avg Duration: 274.8s | Avg Waiting: 103.4s
- **Dynamic Rerouting:** Completed: 24 | Avg Duration: 188.4s | Avg Waiting: 19.1s
- **Key Takeaway:** Heavy trucks suffered the most catastrophic delays in static baseline. Dynamic rerouting successfully guided trucks to destination wards.
