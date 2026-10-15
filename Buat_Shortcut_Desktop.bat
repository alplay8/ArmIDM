@echo off
title Pembuat Shortcut Desktop ArmIDM
set SCRIPT_DIR=%~dp0
set VBS_TEMP=%TEMP%\CreateArmIDMShortcut.vbs

(
echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
echo sLinkFile = oWS.SpecialFolders^("Desktop"^) ^& "\ArmIDM Download Manager.lnk"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
echo If CreateObject^("Scripting.FileSystemObject"^).FileExists^("%SCRIPT_DIR%ArmIDM.exe"^) Then
echo     oLink.TargetPath = "%SCRIPT_DIR%ArmIDM.exe"
echo Else
echo     oLink.TargetPath = "wscript.exe"
echo     oLink.Arguments = "//B " ^& Chr^(34^) ^& "%SCRIPT_DIR%ArmIDM_Silent_Launcher.vbs" ^& Chr^(34^)
echo End If
echo oLink.WorkingDirectory = "%SCRIPT_DIR%"
echo oLink.IconLocation = "%SCRIPT_DIR%armidm.ico"
echo oLink.Description = "ArmIDM - Internet Download Manager (Free Edition)"
echo oLink.Save
) > "%VBS_TEMP%"

cscript //nologo "%VBS_TEMP%"
del "%VBS_TEMP%"
echo Shortcut "ArmIDM Download Manager" dengan ikon resmi berhasil dibuat di Desktop Anda!
pause
