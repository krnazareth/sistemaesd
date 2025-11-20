@echo off
echo ---------------------------------------------------
echo INICIANDO O SISTEMA DO EDUCANDARIO SONHO DOURADO...
echo ---------------------------------------------------
echo.
echo Por favor, nao feche esta janela enquanto usar o sistema.
echo Se o navegador nao abrir, atualize a pagina (F5).
echo.
cd /d "%~dp0"
python -m streamlit run app.py
pause