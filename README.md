# FLEXON Render E-commerce

## What this version includes
- Premium responsive customer storefront
- Professional styled Admin Dashboard
- Product add/edit/delete
- Original Price + Offer/Sale Price + automatic discount percentage
- Cart and quantity updates
- Checkout with Cash on Delivery
- Order number generation
- Customer order tracking page
- Admin order status updates
- Email on order creation and status update (SMTP)
- Stock reduction when an order is placed
- PostgreSQL-ready for Render production

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`

Default admin for local testing:
- username: `admin`
- password: `admin123`

## Deploy on Render
1. Upload this project to a GitHub repository.
2. Create a PostgreSQL database on a provider that gives you a connection URL.
3. In Render, create a **Web Service** from your GitHub repository.
4. Build command:
   `pip install -r requirements.txt`
5. Start command:
   `gunicorn app:app`
6. Add Environment Variables:
   - `SECRET_KEY` = a long random value
   - `DATABASE_URL` = your PostgreSQL connection URL
   - `ADMIN_USERNAME` = your chosen admin username
   - `ADMIN_PASSWORD` = a strong password

### Email notifications
Set:
- `SMTP_HOST`
- `SMTP_PORT` (usually 587)
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`

For Gmail, use an App Password rather than your normal Gmail password.

## Important production notes
- Do not use the default admin password in production.
- Render's temporary local filesystem is not suitable for permanent SQLite business data. Use PostgreSQL through `DATABASE_URL`.
- This project uses image URLs for products, so product images do not disappear when the server restarts.
- Before accepting online card/mobile-wallet payments, use an appropriate trusted payment provider and server-side verification.
