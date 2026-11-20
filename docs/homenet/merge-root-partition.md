# Merge `/srv/state` into the root partition (mr-ray)

Goal: delete the empty `/srv/state` partition (`nvme0n1p1`, 76 GB) and grow the Linux root
(`nvme0n1p5`, 40 GB) to fill the whole NVMe (~117 GB).

Why a USB stick is needed: the free space sits *before* the root partition. Growing toward the
front means moving the running system, which can only be done while booted from something else.

Checked 2026-11-20 before writing this:
- The Ubuntu 24.04 USB stick (`sda`, label `UBUNTU 24_0`) is plugged in, and its boot entry is `Boot0004`.
- GRUB finds root by filesystem UUID (`045573ad-…`). Moving or resizing keeps that UUID, so booting won't break.
- `/srv/state` is empty (only `lost+found`).

**Time:** about 20–30 min, with the server offline (website and services down).
**Need:** a monitor and keyboard on the mini PC, and the Ethernet cable plugged in.
**Risk:** a power cut *while GParted is moving the partition* can corrupt root. Don't touch the machine during that step.

> Open this file on your Mac or phone (GitHub, or `cat` it over SSH beforehand). You won't have SSH during Part 2.

---

## Part 1: Prepare (over SSH, system running)

**1. Back up the important parts of root to the external drive:**
```bash
sudo tar czf /srv/data/mr-ray-backup-2026-11-20.tar.gz /etc /home/cskin/Cesium /home/cskin/.ssh
ls -lh /srv/data/mr-ray-backup-2026-11-20.tar.gz
```
The code is also on GitHub (`Cesium-Lab/heart`). Commit and push anything uncommitted if you want it there too.

**2. Remove `/srv/state` from fstab and unmount it:**
```bash
sudo cp /etc/fstab /etc/fstab.bak2
sudo sed -i '\#/srv/state#d' /etc/fstab
sudo umount /srv/state
grep srv /etc/fstab     # should show only the /srv/data line
```
The `/srv/state` folder stays as an ordinary folder on root, which is fine.

**3. Boot from the USB stick once (next boot only):**
```bash
sudo efibootmgr --bootnext 0004
```

**4. Unplug the Samsung drive** so it can't be picked by mistake.

**5. Plug the monitor and keyboard into the mini PC, then reboot:**
```bash
sudo reboot
```
SSH will drop. Everything after this happens at the mini PC.

---

## Part 2: GParted (at the mini PC)

**6.** A boot menu appears. Choose **"Try or Install Ubuntu"**.

**7.** When the installer window opens, close it, or choose "Try Ubuntu". You want the live desktop.

**8.** Open a terminal (Ctrl+Alt+T) and start GParted:
```bash
which gparted || (sudo apt update && sudo apt install -y gparted)
sudo gparted
```

**9.** In the dropdown at the top right, select **`/dev/nvme0n1` (119 GB)**, *not* `/dev/sda` (the 7.4 GB USB stick). You should see:

| Partition | Size | Filesystem | Label/flags |
| --- | --- | --- | --- |
| unallocated | 129 MiB | | |
| `/dev/nvme0n1p1` | 76 GB | ext4 | label `state` |
| `/dev/nvme0n1p2` | 100 MiB | fat32 | boot, esp. **Don't touch.** |
| `/dev/nvme0n1p5` | 40 GB | ext4 | Linux system |
| unallocated | 1.8 GB | | |

A key icon means the partition is mounted. Right-click it and choose **Unmount**.

**10. Delete `/srv/state`.** Right-click `/dev/nvme0n1p1` (76 GB, label `state`) and choose **Delete**. Check that the label says `state`.

**11. Grow the root partition.** Right-click `/dev/nvme0n1p5` and choose **Resize/Move**. Set:
- **Free space preceding:** `0`. GParted may round this to keep alignment, which is fine.
- **Free space following:** `0`.
- **New size:** fills in automatically (about 119,600 MiB).

Click **Resize/Move**. GParted warns that moving the start of a partition can stop it booting. That's
expected and safe here, because GRUB finds root by UUID. Click **OK**.

**12. Click the green ✓ (Apply All Operations), then Apply.** GParted deletes, moves, then grows.
It moves only the ~27 GB of used data, so expect a few minutes. **Don't power off.**
Wait for "All operations successfully completed".

**13. (Optional, recommended)** Right-click the root partition, choose **Check**, then Apply. This runs a filesystem check.

**14.** Close GParted, shut down, pull out the USB stick when prompted, and power back on. It boots from the internal disk normally.

---

## Part 3: Confirm (over SSH again)

**15.** Plug the Samsung drive back in, then:
```bash
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS /dev/nvme0n1
df -h /
ls /srv/data
systemctl --failed
```
Expected:
- `nvme0n1p5` is about 117 GB and mounted at `/`. It keeps the name `p5`, which is normal.
- Root is about 23% used.
- The drive's folders are listed under `/srv/data`.
- There are no failed services.

Then update `CLAUDE.md` (the "The machine" and "Storage" sections still describe `/srv/state` as its own partition).

---

## If it doesn't boot

If it lands at a `grub>` or `grub rescue>` prompt, boot the USB stick again ("Try Ubuntu"), open a terminal and run:
```bash
sudo mount /dev/nvme0n1p5 /mnt
sudo mount /dev/nvme0n1p2 /mnt/boot/efi
for d in dev proc sys; do sudo mount --bind /$d /mnt/$d; done
sudo chroot /mnt grub-install
sudo chroot /mnt update-grub
```
Then reboot.

If the filesystem itself is damaged, the backup from step 1 has `/etc` and the project. The files on
the Samsung drive aren't touched by any of this.
