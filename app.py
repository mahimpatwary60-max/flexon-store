import os, uuid, smtplib
from datetime import datetime
from email.message import EmailMessage
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret")
database_url = os.getenv("DATABASE_URL", "sqlite:///flexon.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    category = db.Column(db.String(80), default="Fashion")
    description = db.Column(db.Text, default="")
    image_url = db.Column(db.String(1000), default="")
    original_price = db.Column(db.Integer, nullable=False)
    sale_price = db.Column(db.Integer, nullable=False)
    stock = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def discount_percent(self):
        if self.original_price and self.sale_price < self.original_price:
            return round((1 - self.sale_price / self.original_price) * 100)
        return 0

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(30), unique=True, nullable=False)
    customer_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), default="")
    phone = db.Column(db.String(40), nullable=False)
    address = db.Column(db.Text, nullable=False)
    note = db.Column(db.Text, default="")
    total = db.Column(db.Integer, default=0)
    delivery_charge = db.Column(db.Integer, default=0)
    status = db.Column(db.String(40), default="Pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_name = db.Column(db.String(180), nullable=False)
    product_id = db.Column(db.Integer, nullable=True)
    price = db.Column(db.Integer, nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)

def money(v):
    return f"৳{int(v):,}"

app.jinja_env.globals["money"] = money

def slugify(name):
    base = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    return f"{base}-{uuid.uuid4().hex[:6]}"

def cart_data():
    raw = session.get("cart", {})
    products = []
    subtotal = 0
    for key, qty in raw.items():
        p = db.session.get(Product, int(key))
        if p and p.active and p.stock > 0:
            qty = max(1, min(int(qty), p.stock))
            subtotal += p.sale_price * qty
            products.append((p, qty))
    return products, subtotal

@app.context_processor
def inject_cart():
    return {"cart_count": sum(int(x) for x in session.get("cart", {}).values())}

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapped

def send_order_email(order, event):
    if not order.email:
        return
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    port = int(os.getenv("SMTP_PORT", "587"))
    sender = os.getenv("SMTP_FROM", user or "noreply@example.com")
    if not all([host, user, password]):
        return

    if event == "created":
        subject = f"FLEXON Order Received — {order.order_no}"
        body = f"""Hi {order.customer_name},

Thanks for shopping with FLEXON!
We received your order.

Order: {order.order_no}
Total: {money(order.total + order.delivery_charge)}
Status: {order.status}

Track your order on our website using your order number and email.

FLEXON — Wear Your Flex
"""
    else:
        subject = f"FLEXON Order Update — {order.order_no}"
        body = f"""Hi {order.customer_name},

Your FLEXON order has been updated.

Order: {order.order_no}
New status: {order.status}

Thank you for shopping with FLEXON.
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = order.email
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
    except Exception as e:
        app.logger.warning("Email failed: %s", e)

@app.route("/")
def home():
    category = request.args.get("category", "")
    q = request.args.get("q", "").strip()
    query = Product.query.filter_by(active=True)
    if category:
        query = query.filter(Product.category == category)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    products = query.order_by(Product.featured.desc(), Product.created_at.desc()).all()
    categories = [x[0] for x in db.session.query(Product.category).filter_by(active=True).distinct().all()]
    return render_template("home.html", products=products, categories=categories, category=category, q=q)

@app.route("/product/<int:product_id>")
def product(product_id):
    p = db.session.get_or_404(Product, product_id)
    return render_template("product.html", p=p)

@app.post("/cart/add/<int:product_id>")
def add_cart(product_id):
    p = db.session.get_or_404(Product, product_id)
    if p.stock < 1:
        flash("This product is currently out of stock.", "error")
        return redirect(request.referrer or url_for("home"))
    cart = session.get("cart", {})
    cart[str(product_id)] = min(int(cart.get(str(product_id), 0)) + 1, p.stock)
    session["cart"] = cart
    flash("Added to cart!", "success")
    return redirect(request.referrer or url_for("cart"))

@app.route("/cart")
def cart():
    items, subtotal = cart_data()
    return render_template("cart.html", items=items, subtotal=subtotal)

@app.post("/cart/update")
def cart_update():
    cart = session.get("cart", {})
    for key in list(cart.keys()):
        qty = request.form.get(f"qty_{key}")
        if qty is not None:
            try:
                qty = int(qty)
            except ValueError:
                qty = 1
            if qty <= 0:
                cart.pop(key, None)
            else:
                p = db.session.get(Product, int(key))
                cart[key] = min(qty, p.stock) if p else qty
    session["cart"] = cart
    flash("Cart updated.", "success")
    return redirect(url_for("cart"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, subtotal = cart_data()
    if not items:
        flash("Your cart is empty.", "error")
        return redirect(url_for("home"))

    delivery = 80
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        note = request.form.get("note", "").strip()
        if not name or not phone or not address:
            flash("Name, phone and address are required.", "error")
            return redirect(url_for("checkout"))

        order = Order(
            order_no="FX-" + uuid.uuid4().hex[:8].upper(),
            customer_name=name, email=email, phone=phone, address=address,
            note=note, total=subtotal, delivery_charge=delivery, status="Pending"
        )
        db.session.add(order)
        for p, qty in items:
            if p.stock < qty:
                db.session.rollback()
                flash(f"{p.name} is no longer available in the requested quantity.", "error")
                return redirect(url_for("cart"))
            p.stock -= qty
            db.session.add(OrderItem(order=order, product_name=p.name, product_id=p.id, price=p.sale_price, qty=qty))
        db.session.commit()
        session["cart"] = {}
        send_order_email(order, "created")
        return redirect(url_for("order_success", order_no=order.order_no))

    return render_template("checkout.html", items=items, subtotal=subtotal, delivery=delivery)

@app.route("/order-success/<order_no>")
def order_success(order_no):
    order = Order.query.filter_by(order_no=order_no).first_or_404()
    return render_template("order_success.html", order=order)

@app.route("/track", methods=["GET", "POST"])
def track_order():
    order = None
    searched = False
    if request.method == "POST":
        searched = True
        order_no = request.form.get("order_no", "").strip().upper()
        email = request.form.get("email", "").strip()
        q = Order.query.filter_by(order_no=order_no)
        if email:
            q = q.filter(func.lower(Order.email) == email.lower())
        order = q.first()
        if not order:
            flash("Order not found. Check your order number and email.", "error")
    return render_template("track.html", order=order, searched=searched)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username")
        pw = request.form.get("password")
        if user == os.getenv("ADMIN_USERNAME", "admin") and pw == os.getenv("ADMIN_PASSWORD", "admin123"):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("admin_login.html")

@app.route("/admin")
@admin_required
def admin_dashboard():
    products = Product.query.order_by(Product.created_at.desc()).all()
    orders = Order.query.order_by(Order.created_at.desc()).all()
    revenue = db.session.query(func.coalesce(func.sum(Order.total + Order.delivery_charge), 0)).filter(Order.status != "Cancelled").scalar()
    return render_template("admin_dashboard.html", products=products, orders=orders, revenue=revenue)

@app.route("/admin/product/new", methods=["GET", "POST"])
@admin_required
def admin_product_new():
    if request.method == "POST":
        p = Product(
            name=request.form["name"].strip(),
            slug=slugify(request.form["name"]),
            category=request.form.get("category", "Fashion").strip(),
            description=request.form.get("description", ""),
            image_url=request.form.get("image_url", ""),
            original_price=int(request.form.get("original_price", 0)),
            sale_price=int(request.form.get("sale_price", 0)),
            stock=int(request.form.get("stock", 0)),
            active="active" in request.form,
            featured="featured" in request.form,
        )
        if p.sale_price <= 0 or p.original_price <= 0:
            flash("Prices must be greater than 0.", "error")
            return redirect(url_for("admin_product_new"))
        if p.sale_price > p.original_price:
            flash("Offer price should not be higher than original price.", "error")
            return redirect(url_for("admin_product_new"))
        db.session.add(p); db.session.commit()
        flash("Product added successfully.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_product_form.html", p=None)

@app.route("/admin/product/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_product_edit(product_id):
    p = db.session.get_or_404(Product, product_id)
    if request.method == "POST":
        p.name=request.form["name"].strip()
        p.category=request.form.get("category", "Fashion").strip()
        p.description=request.form.get("description", "")
        p.image_url=request.form.get("image_url", "")
        p.original_price=int(request.form.get("original_price", 0))
        p.sale_price=int(request.form.get("sale_price", 0))
        p.stock=int(request.form.get("stock", 0))
        p.active="active" in request.form
        p.featured="featured" in request.form
        db.session.commit()
        flash("Product updated.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_product_form.html", p=p)

@app.post("/admin/product/<int:product_id>/delete")
@admin_required
def admin_product_delete(product_id):
    p = db.session.get_or_404(Product, product_id)
    db.session.delete(p); db.session.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/order/<int:order_id>/status")
@admin_required
def admin_order_status(order_id):
    order = db.session.get_or_404(Order, order_id)
    status = request.form.get("status")
    allowed = ["Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled"]
    if status in allowed:
        order.status = status
        db.session.commit()
        send_order_email(order, "status")
        flash("Order status updated. Email is sent if SMTP is configured.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("home"))

def seed():
    if Product.query.count() == 0:
        samples = [
            ("FLEXON Premium Black Tee","T-Shirt","Premium cotton streetwear t-shirt.","https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=900&q=80",1290,890,30,True),
            ("FLEXON Urban Oversize Tee","T-Shirt","Comfortable oversize fit for everyday wear.","https://images.unsplash.com/photo-1503341504253-dff4815485f1?auto=format&fit=crop&w=900&q=80",1490,990,20,True),
            ("FLEXON Signature Hoodie","Hoodie","Soft premium hoodie with modern streetwear styling.","https://images.unsplash.com/photo-1556821840-3a63f95609a7?auto=format&fit=crop&w=900&q=80",2490,1990,15,True),
        ]
        for name,cat,desc,img,op,sp,stock,featured in samples:
            db.session.add(Product(name=name,slug=slugify(name),category=cat,description=desc,image_url=img,original_price=op,sale_price=sp,stock=stock,featured=featured))
        db.session.commit()

with app.app_context():
    db.create_all()
    seed()

if __name__ == "__main__":
    app.run(debug=True)
