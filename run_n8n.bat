@echo off
REM Uses a portable Node 22 (n8n needs <=22; this machine's system Node is v25, incompatible)
REM and a locally-installed n8n (no admin rights required for either).
set N8N_USER_MANAGEMENT_DISABLED=true
set NODE="C:\Users\linga\Downloads\project2\.tools\node-v22.23.2-win-x64\node.exe"
set N8N_BIN="C:\Users\linga\Downloads\project2\.tools\n8n-app\node_modules\n8n\bin\n8n"
%NODE% %N8N_BIN% start
