# lookBOOK Demo Lab (Ant Design)

React + [Ant Design](https://ant.design) shell for the Gen 2 lab API. Replaces `alert()` / `prompt()` with Modal, Drawer, and `message`.

## Dev

```powershell
pip install -e "..\[lab]"
pwsh ..\scripts\start-demo-lab.ps1
cd demo-lab-react
npm install
# If build fails on Windows with missing @rc-component/*, run:
# npm install @rc-component/mini-decimal
npm run dev
```

Open http://localhost:5173 (API proxied to :8042).

## Production build (served by lab_server)

```powershell
npm run build
python -m lookbook.lab_server
```

Open http://127.0.0.1:8042/react/

Legacy vanilla UI remains at http://127.0.0.1:8042/

## Skill

Portfolio agent workflow: `D:\projects\skills\ant-design\SKILL.md`