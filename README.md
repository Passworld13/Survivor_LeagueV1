# Survivor Pass WebApp

This repository contains a simple **Survivor Pass WebApp** built with 
vanilla HTML, CSS, and JavaScript. The app allows users to connect their 
Phantom (Solana) wallet and purchase a **SURVIVOR PASS** NFT, designed to 
be opened as a Telegram WebApp.

## Features

- **Phantom Wallet Connection:** Users can connect their Phantom Wallet 
via the `Connect Phantom Wallet` button. After connecting, the app 
requests the user to sign a message to verify ownership of the wallet.
- **Buy Survivor Pass:** Users can click the `Buy SURVIVOR PASS` button to 
be redirected to Crossmint for purchasing the NFT.
- **Telegram Integration:** Upon successful connection and signing, the 
app sends the wallet address and signature back to the Telegram bot using 
`window.Telegram.WebApp.sendData`.
- **Minimal Design:** The interface is clean and minimal — light 
background, simple buttons, and no additional clutter. All text is in 
English.
- **No Frameworks:** The project uses plain HTML/CSS/JS (no React, Vue, 
etc.), making it lightweight and easy to deploy.

## File Structure

- **public/index.html:** Main HTML page containing the UI and buttons.
- **public/style.css:** Stylesheet defining the look and feel (layout, 
colors, buttons).
- **public/script.js:** JavaScript logic for wallet connection, signing, 
and Telegram integration.
- **vercel.json:** Configuration file for deploying on Vercel (static 
deployment).
- **README.md:** Documentation and deployment instructions (this file).

## How to Deploy on Vercel

Deploying this webapp on Vercel is straightforward:

1. **Clone the Repository:** Clone or download the repository to your 
local machine.
2. **Vercel Account:** Ensure you have an account on 
[Vercel](https://vercel.com/) and the Vercel CLI installed (optional).
3. **Import Project:** In the Vercel dashboard, import the project (if 
using GitHub, GitLab, etc.) or use `vercel deploy` via CLI.
4. **Project Settings:** No build step is required (it's a static site). 
If needed, set the **Framework Preset** to **None** (Static Site).  
   - The content is in the `public` directory. Vercel should detect and 
serve this automatically. If not, set the **Output Directory** to `public` 
in the Vercel project settings.
5. **Deploy:** Once imported, trigger a deploy. Vercel will upload the 
files in `public/` and make the site available at a generated URL (or your 
chosen custom domain).
6. **Verify:** Open the deployed URL. You should see the Survivor Pass 
page with the two buttons. Ensure that the site loads the JavaScript and 
CSS correctly (the included **vercel.json** helps serve the public 
folder).

## Using the WebApp in Telegram

This webapp is intended to be launched from a Telegram bot as a [Web 
App](https://core.telegram.org/bots/webapps). To integrate:
- In your Telegram Bot, use a button (keyboard button or inline button) 
with the `WebApp` property to open the URL of this webapp. For example, 
using Bot API you can set a 
[KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton) or 
[InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton) 
with the `web_app` field pointing to your Vercel deployment URL.
- When the user taps the button in Telegram, this webapp will open within 
the Telegram interface.
- After the user connects their wallet, the webapp will send the data 
(wallet address & signature) back to your bot via 
`Telegram.WebApp.sendData`. Your bot can receive this data as an update 
(check for `WebAppData` in the incoming message). You should parse the 
JSON string and verify the signature on your server to authenticate the 
user’s wallet.
- **Note:** Ensure the Phantom wallet is available in the environment 
where the Telegram WebApp is opened. (On desktop Telegram, it will open in 
a browser where the Phantom extension is installed. On mobile, Phantom 
must be installed and able to interact with the in-app browser, or the 
user may need to use Telegram Web or Desktop.)

## Customization

- **Crossmint Link:** The `Buy SURVIVOR PASS` button currently points to 
`https://www.crossmint.com`. You should update this href to the specific 
Crossmint checkout URL or page for your Survivor Pass NFT (if available). 
This could be a direct link to your collection’s purchase page on 
Crossmint.
- **Styling:** You can adjust `public/style.css` to change colors, 
spacing, or add your branding (logo, etc.) as needed, while keeping the 
design minimal.
- **Message Signing:** The message being signed is `"SURVIVOR PASS 
Verification"`. You can modify this if necessary. Just ensure your 
Telegram bot knows what message to expect when verifying the signature.

## Security Considerations

- The webapp generates a signature of a fixed message. For a production 
scenario, you might want to use a one-time nonce from the server to 
prevent replay attacks (i.e., have the bot supply a unique message for 
each session). In this simple implementation, a static message is used for 
demonstration.
- Always verify the signature in a secure environment (your bot server) 
using the wallet’s public key. For Solana, you can use libraries like 
`TweetNacl` to verify the signature matches the message and public key.
- The `window.Telegram.WebApp.sendData` method should be used to send 
non-sensitive data. Do not send private keys or secrets. Here we only send 
the public wallet address and the signature.

## License

This project is provided as-is for integration with the Survivor League 
bot. You may modify or extend it to fit your needs. Be sure to test 
thoroughly, especially the Telegram integration and Phantom wallet 
connection, in the environment where it will be used.


