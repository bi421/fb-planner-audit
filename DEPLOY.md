# Render.com Deploy Checklist

1. Push code to GitHub:
   git push -u origin main

2. Go to https://dashboard.render.com/web/new
   - Select "Web Service"
   - Connect your GitHub repo: fb-planner-v2
   - Name: fb-planner-v2
   - Runtime: Python 3
   - Build Command: pip install -r requirements.txt
   - Start Command: python run.py

3. Environment Variables (in Render dashboard or render.yaml):
   - META_TOKEN = <your meta token>
   - QPAY_KEY = <your qpay key>

4. Deploy and wait for build to complete.

5. Set Facebook/Meta Webhook URL:
   https://your-app-name.onrender.com/webhook
   Verify Token: fbplanner_verify

6. Test health endpoint:
   https://your-app-name.onrender.com/

7. Confirm webhook verification works on Meta developer console.
