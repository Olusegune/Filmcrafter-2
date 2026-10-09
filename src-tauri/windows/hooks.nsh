; FilmCrafter installer hooks: give .filmcrafter and .pulse project files their own document icon.
; The file class name matches bundle.fileAssociations[].name in tauri.conf.json.

!macro NSIS_HOOK_POSTINSTALL
  WriteRegStr SHCTX "Software\Classes\FilmCrafter.Project\DefaultIcon" "" "$\"$INSTDIR\document.ico$\""
  WriteRegStr SHCTX "Software\Classes\FilmCrafter.Package\DefaultIcon" "" "$\"$INSTDIR\document.ico$\""
  WriteRegStr SHCTX "Software\Classes\FilmCrafter.Producer\DefaultIcon" "" "$\"$INSTDIR\document.ico$\""
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
!macroend
