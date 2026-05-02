# 常用命令

## Git 推送到 GitHub

```bash
# 代理可用时直接推
git add -A
git commit -m "提交说明"
git push origin main

# 代理不可用时（绕过 Clash 7897 端口）
git add -A
git commit -m "提交说明"
git -c http.proxy="" -c https.proxy="" push origin main

# 如果远程有新提交，先拉再推
git -c http.proxy="" -c https.proxy="" pull origin main --rebase
git -c http.proxy="" -c https.proxy="" push origin main
```

## 清理 __pycache__

```bash
# Linux/Git Bash
find . -type d -name "__pycache__" ! -path "./.venv/*" | xargs rm -rf

# PowerShell
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Where-Object { $_.FullName -notlike "*\.venv\*" } | Remove-Item -Recurse -Force
```

## 启动项目

```bash
# 纯 HMI 测试（Mock 数据，无需 CARLA）
python main.py --hmi-only

# Web HMI + AI（Mock 数据）
python main.py --web-hmi --mock-carla

# Web HMI + CARLA + AI（完整模式）
python main.py --web-hmi

# Web HMI + CARLA（无 AI）
python main.py --web-hmi --no-ai

# 传统模式（CARLA + TCP Unity）
python main.py
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 查看 Git 状态

```bash
git status
git log --oneline -10
```
