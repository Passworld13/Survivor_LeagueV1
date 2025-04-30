// Ensure the script runs after the DOM is loaded
window.addEventListener("DOMContentLoaded", function() {
  const connectBtn = document.getElementById("connectBtn");
  const buyBtn = document.getElementById("buyBtn");
  const errorMsg = document.getElementById("errorMsg");

  // Check if Phantom (Solana wallet) is installed
  const phantom = window.solana;
  if (!phantom || !phantom.isPhantom) {
    // Phantom extension not found
    errorMsg.textContent = "Phantom Wallet is not installed. Please install Phantom to continue.";
    errorMsg.style.display = "block";
    // Disable the connect button since no wallet is available
    connectBtn.disabled = true;
  }

  // On Connect button click
  connectBtn.addEventListener("click", async function() {
    try {
      // Connect to Phantom wallet (will prompt the user)&#8203;:contentReference[oaicite:4]{index=4}
      const response = await window.solana.connect();
      const publicKey = response.publicKey.toString();
      console.log("Connected to wallet:", publicKey);

      // Define a message for the user to sign for verification
      const message = "SURVIVOR PASS Verification";
      const encodedMessage = new TextEncoder().encode(message);

      // Sign the message with the wallet (user will approve in Phantom)&#8203;:contentReference[oaicite:5]{index=5}
      const signed = await window.solana.signMessage(encodedMessage, "utf8");
      // `signed.signature` is a Uint8Array containing the signature
      // Convert signature to base64 string for sending
      const signatureArray = signed.signature;           // Uint8Array
      let signatureBase64 = "";
      try {
        // Convert Uint8Array to base64
        signatureBase64 = btoa(String.fromCharCode(...signatureArray));
      } catch (e) {
        console.error("Base64 encoding failed:", e);
      }

      // Prepare data as JSON string
      const dataToSend = JSON.stringify({
       action: "wallet_connected",
       wallet: publicKey,
       signature: signatureBase64
      });

      console.log("Sending data to Telegram:", dataToSend);

      // Send the wallet address and signature to the Telegram bot
      window.Telegram.WebApp.sendData(dataToSend);
      // Optionally, indicate success to the user (e.g., disable button or show a message)
      connectBtn.textContent = "Wallet Connected ✓";
      connectBtn.disabled = true;
    } catch (err) {
      console.error("Wallet connection or signing failed:", err);
      alert("Error: " + (err.message || err));
    }
  });

  // On Buy button click (optional: we rely on anchor's default behavior to open Crossmint)
  buyBtn.addEventListener("click", function() {
    // You could add any tracking or pre-check here if needed.
    // By default, the anchor will open Crossmint in a new tab.
    console.log("Redirecting to Crossmint for purchase...");
  });
});

