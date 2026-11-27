# Minor

#### Added

- **A message from a lemon's web page can take files.** The paperclip, a paste or a drop adds files to the draft without sending it; each shows above the box, an image as a thumbnail and any other file as a card, with a button to remove it, and they go with the message when you press send. An OpenClaw lemon gets the files through `chat.send`; any other lemon gets their paths on the server, where they are kept for 30 days.

#### Changed

- **A lemon's web page writes messages in a box like a chat app's.** It is rounded, grows with what you type, has the paperclip at its left and, on a wide screen, a round send at its right. It says how a message goes in only when it goes as mail. An OpenClaw lemon's conversation shows the files sent with each message.
