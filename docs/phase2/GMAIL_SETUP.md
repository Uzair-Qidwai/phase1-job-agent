# Personal Gmail sender for the controlled test

The Penn address can receive the test digest without authorizing an OAuth app.
Use a personal Gmail account to send it. Setup itself sends nothing.

1. In a Google Cloud project you control, enable the Gmail API.
2. Configure Google Auth Platform branding/audience. For an external app in
   Testing, add your personal Gmail address as a test user.
3. Create an OAuth client of type **Desktop app** and download its JSON to
   `.local/gmail-client.json` in this checkout. This ignored file is a credential;
   do not commit or share it. An API key is not a Gmail OAuth credential.
4. Run the local helper, replacing the sender address:

   ```bash
   .venv/bin/python scripts/configure_gmail.py \
     --client-file .local/gmail-client.json \
     --sender YOUR_PERSONAL_GMAIL_ADDRESS \
     --recipient qidwai@engineering.upenn.edu
   ```

   Sign in to the personal sender account in the browser. The helper requests
   only Gmail send access and saves the refresh token to ignored `.env`, with
   owner-only permissions. It does not print the credentials or send mail.

5. Once configured, the authorized single test uses a fresh isolated local DB:

   ```bash
   .venv/bin/python -m evals.delivery_smoke --allow-send \
     --recipient qidwai@engineering.upenn.edu \
     --output .local/delivery-live-01.json
   ```

   The disposable PostgreSQL instance must be running on port 55439. This sends
   one clearly fictional job via the normal durable delivery boundary. It never
   loads backlog, scrapes, or calls a model. Confirm receipt in the inbox after
   transport acknowledgement. On uncertainty, retain the database/report and
   reconcile the recorded attempt; do not simply run another test.

Google setup reference: [Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python).
The quickstart uses read access for its sample; our helper requests send access
only. OAuth testing-mode token lifetime must be resolved before an unattended
production schedule; see Google's [OAuth token expiration guidance](https://developers.google.com/identity/protocols/oauth2#expiration).
