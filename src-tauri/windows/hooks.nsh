!macro NSIS_HOOK_PREINSTALL
  ; Kill running PharmacySuite processes before installing
  ; /F = force, /T = tree kill (child processes), /IM = image name
  nsExec::ExecToStack 'taskkill /F /T /IM app.exe'
  Pop $0
  nsExec::ExecToStack 'taskkill /F /T /IM node.exe'
  Pop $0
  nsExec::ExecToStack 'taskkill /F /T /IM backend.exe'
  Pop $0
  Sleep 1000
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ; Kill running PharmacySuite processes before uninstalling
  nsExec::ExecToStack 'taskkill /F /T /IM app.exe'
  Pop $0
  nsExec::ExecToStack 'taskkill /F /T /IM node.exe'
  Pop $0
  nsExec::ExecToStack 'taskkill /F /T /IM backend.exe'
  Pop $0
  Sleep 1000
!macroend
