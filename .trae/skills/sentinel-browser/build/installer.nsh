; NSIS Installer Script for Sentinel Browser
; Custom installer logic for Windows

!macro customHeader
  ; 设置安装程序标题
  Name "Sentinel Browser"
!macroend

!macro customInstall
  ; 创建必要的目录
  CreateDirectory "$INSTDIR\userdata"
  CreateDirectory "$INSTDIR\output"
  
  ; 设置目录权限
  AccessControl::GrantOnFile "$INSTDIR\userdata" "(BU)" "GenericRead + GenericWrite"
  AccessControl::GrantOnFile "$INSTDIR\output" "(BU)" "GenericRead + GenericWrite"
!macroend

!macro customUnInstall
  ; 卸载时询问是否删除用户数据
  MessageBox MB_YESNO "是否删除用户数据目录？$\r$\n这将会删除所有已保存的任务数据。" IDNO skipDeleteData
    RMDir /r "$INSTDIR\userdata"
    RMDir /r "$INSTDIR\output"
  skipDeleteData:
!macroend
