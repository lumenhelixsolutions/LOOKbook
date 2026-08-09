# Demo Lab

Start the combined API + UI server (recommended):

```powershell
cd D:\projects\lookBOOK
python -m lookbook.lab_server
# or: python scripts/run_demo_lab.py
```

Open **http://localhost:8042/** (not port 8766, and not bare `file://`).

Legacy path **http://localhost:8042/demo-lab/index.html** also works.

The lab generates a true-animation handoff packet from a dropped image/keyframe when the Python pipeline is reachable.
