#!/bin/sh

# By this script, SONiC switch moving to ONIE with specific boot_mode
# The examples of usage:
#     onie_reboot.sh install
#     onie_reboot.sh update


onie_mount=/mnt/onie-boot
onie_lib=/lib/onie
os_boot=/host

enable_onie_access() {
  if ! test -d ${onie_mount}; then
    mkdir -p ${onie_mount}
  fi

  if ! mountpoint -q "${onie_mount}"; then
    mount LABEL="ONIE-BOOT" ${onie_mount}
  fi

  if ! test -e ${onie_lib}; then
    ln -s ${onie_mount}/onie/tools/lib/onie ${onie_lib}
  fi
}

disable_onie_access() {
  if test -e ${onie_lib}; then
    unlink ${onie_lib}
  fi

  if mountpoint -q ${onie_mount}; then
    umount -rf ${onie_mount}
  fi

  if test -d ${onie_mount}; then
    rmdir ${onie_mount}
  fi
}

# ONIE entry must exist in grub config
find_onie_menuentry() {
  onie_entry="$(cat $os_boot/grub/grub.cfg | grep -e 'menuentry' | cat -n | awk '$0~/ONIE/ {print $1-1}')"
  entries_num="$(echo "$onie_entry" | grep -E '^[0-9]+$' | wc -l)"
  if [ $entries_num -eq 1 ] && [ $onie_entry -ge 1 ]; then
    return 0
  fi
  return 1
}

change_grub_boot_order() {
  find_onie_menuentry
	rc=$?
	if [ $rc -eq 0 ]; then
	  grub-reboot --boot-directory=$os_boot $onie_entry
	else
	  echo "ERROR: ONIE entry wasn't found in grub config"
	  return 1
	fi

  echo "INFO: Set onie mode to $1"
  if ! test -f ${os_boot}/grub/grubenv || ! test -f ${onie_mount}/grub/grubenv; then
    return 1
  fi

  if test -d /sys/firmware/efi/efivars && efibootmgr > /dev/null 2>&1; then
    echo "Set next boot EFI system"
    # get ONIE boot number
    boot_num=$(efibootmgr | grep "ONIE:" | awk '{ print $1 }' | cut -b 5-8 )
    efibootmgr -n $boot_num
  else
    echo "Set next boot Regular system"
    grub-editenv ${os_boot}/grub/grubenv set onie_entry="ONIE" || return $?
  fi

  # set onie_mode in onie_mount's grubenv
  if ! grub-editenv ${onie_mount}/grub/grubenv set onie_mode=$1; then
    echo "WARNING: Failed to set onie_mode in ${onie_mount}/grub/grubenv"
    # Ensure onie_mode fits into the existing grubenv block
    echo "INFO: Manual set onie_mode in ${onie_mount}/grub/grubenv"
    if ! grep -q "onie_mode=" ${onie_mount}/grub/grubenv; then
      echo "onie_mode=$1" >> ${onie_mount}/grub/grubenv || return $?
    else
      sed -i "s/onie_mode=.*/onie_mode=$1/" ${onie_mount}/grub/grubenv || return $?
    fi
  fi

  return 0
}

system_reboot() {
  echo "INFO: Rebooting in 3 sec..."
  sleep 3s
  /sbin/reboot
}

enable_onie_access
change_grub_boot_order $1
rc=$?
if [ $rc -eq 0 ]; then
  system_reboot
fi
disable_onie_access

exit $rc
