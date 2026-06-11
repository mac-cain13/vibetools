# FSEvents spike — build-order step zero

Before committing to the board's FSEvents architecture, validate the one
assumption it rests on: **FSEvents fires on the Mac host for
writes that arrive from the VM through the share.** The store lives on the
Mac's local disk and the VM reaches it via the path-aligned symlink
(`/Volumes/External/Repositories` — see `docs/vibeboard-format.md` §1), so VM
writes should land on the local filesystem and trigger FSEvents like any local
write. This spike confirms that empirically.

## What the spike does

`FSEventsSpike` takes one directory argument, watches it with
`FSEventStreamCreate` (file-level events, no polling), and prints one line per
event: timestamp, path, decoded flags, event id.

## Validation procedure

1. **On the Mac host**, build and run the spike against the store directory:

   ```sh
   cd VibeBoard
   swift build
   swift run FSEventsSpike /Volumes/External/Repositories/_vibeboard
   ```

   (Create the directory first if it does not exist yet:
   `mkdir -p /Volumes/External/Repositories/_vibeboard`.)

2. **Local sanity check** (separate Mac terminal) — proves the harness works
   before involving the VM:

   ```sh
   echo "ping $(date)" > /Volumes/External/Repositories/_vibeboard/spike-local.md
   ```

   Expect within ~1s: lines mentioning `spike-local.md` with flags such as
   `created,file` and `modified,file`.

3. **The real test — write from inside the VM through the share.** SSH into
   the VM (the same way `vibe` connects) and write a file via the shared path:

   ```sh
   echo "ping-from-vm $(date)" > /Volumes/External/Repositories/_vibeboard/spike-vm.md
   ```

   Also exercise the two write patterns the ticket writers use, since rename
   semantics can differ from plain writes on shares:

   ```sh
   # atomic update pattern (temp + rename), as used for ticket updates
   echo "v2" > /Volumes/External/Repositories/_vibeboard/.spike-vm.md.tmp
   mv /Volumes/External/Repositories/_vibeboard/.spike-vm.md.tmp \
      /Volumes/External/Repositories/_vibeboard/spike-vm.md

   # appending, as a skill might when adding a note
   echo "appended" >> /Volumes/External/Repositories/_vibeboard/spike-vm.md
   ```

4. **Confirm**: every VM-side write from step 3 produces event lines in the
   spike output on the Mac (allow for the 0.1s coalescing latency; a
   `renamed` flag for the `mv` is expected and fine — the board reloads the
   whole directory on any event, so the specific flags do not matter).

5. Clean up the `spike-*.md` test files.

## Pass / fail

- **Pass:** all three VM-side write patterns produce events on the Mac. The
  board's FSEvents architecture (`TicketStore` + `FSEventsWatcher`) is valid
  as built; no polling needed.
- **Fail (events missing or unreliable):** do **not** add polling. The
  fallback is a **writer-emitted ping** — writers (skill,
  vibe) touch a well-known local path or notify the board directly after a
  write, and the board watches/receives that instead of relying on the
  filesystem to propagate share writes. That keeps the push model and the
  no-polling decision intact; only the event source changes. Re-evaluate the
  `TicketStore` watch wiring (a single seam: `FSEventsWatcher` behind the
  debounced-reload callback) before building further UI on top.

## Notes

- The spike and the board share the same `FSEventsWatcher` implementation, so
  the spike validates exactly the code path the app will rely on.
- `swift run VibeBoard -storePath /tmp/some-store` points the board at a
  different store directory (the `-storePath` launch argument lands in
  `UserDefaults` via the `NSArgumentDomain`); the same trick helps when
  spiking against a scratch directory.
