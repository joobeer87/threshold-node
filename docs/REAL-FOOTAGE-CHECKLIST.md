# Real-house footage privacy checklist

Real footage is a strong demo choice when the room is treated as a film set rather than a
data source. The public repo should still contain only synthetic housefile data.

## Before recording

- Use one staged room; avoid filming a route through the whole home.
- Get permission from every identifiable person and property owner. Avoid minors.
- Remove mail, labels, calendars, prescriptions, financial papers, keys, family photos,
  school or employer material, and objects with names or addresses.
- Hide screens, notification previews, Wi-Fi names, QR codes, serial numbers, device IDs,
  smart-home labels, license plates, and exterior views that reveal location.
- Check mirrors, windows, glossy appliances, picture frames, and robot surfaces for
  reflections.
- Disable camera location tagging and use Do Not Disturb. Record narration separately if
  background voices could identify anyone.
- Use the synthetic Threshold fixture and synthetic actor names on every visible UI.

## During recording

- Frame only what the audience needs to understand the interaction.
- Do not show live terminals with usernames, home paths, network names, environment
  variables, tokens, browser profiles, or private repository history.
- Do not scan or upload the real room into the checked-in demo fixture. If model capture
  is shown, use a narrowly framed shot and discard the raw model input after review.
- Use a clearly synthetic receipt and keep the prototype stop/interlock disclaimer visible
  in supporting material.

## Before upload

1. Review every frame at reduced speed and inspect the first and last frames separately.
2. Review the audio track or transcript for names, addresses, notifications, and voices.
3. Blur or crop anything uncertain; if a detail is not needed, remove the shot.
4. Re-encode without source metadata. One local option is:

   ```bash
   ffmpeg -i input.mov -map_metadata -1 -map_chapters -1 \
     -c:v libx264 -crf 18 -preset medium -c:a aac -b:a 192k reviewed.mp4
   ```

5. Re-run the visual and audio review on `reviewed.mp4`; metadata removal does not redact
   pixels or sound.
6. Upload the approved export to the submission platform or approved video host. Commit a
   link and caption later, not the video or raw footage.

## Release record

Record the reviewer, date, source-file count, approved export hash, and a simple result:
`pass`, `revise`, or `reject`. Do not record private findings in the public receipt. Store
that local review receipt outside Git.
