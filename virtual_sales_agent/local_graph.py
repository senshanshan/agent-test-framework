import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from langchain_core.messages import AIMessage, HumanMessage

from database.db_manager import DatabaseManager


db_manager = DatabaseManager()


@dataclass
class Snapshot:
    values: Dict[str, Any]
    next: tuple = ()


class LocalSalesGraph:
    """Small deterministic graph used when no hosted LLM credentials are present."""

    def stream(
        self, state: Dict[str, Any], config: Dict[str, Any], stream_mode: str = "values"
    ) -> Iterable[Dict[str, Any]]:
        yield self.invoke(state, config)

    def invoke(
        self, state: Optional[Dict[str, Any]], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        messages = (state or {}).get("messages", [])
        user_text = self._last_user_text(messages)
        customer_id = (
            config.get("configurable", {}).get("customer_id", "123456789")
            if config
            else "123456789"
        )
        answer = self._answer(user_text, customer_id)
        return {"messages": list(messages) + [AIMessage(content=answer)]}

    def get_state(self, config: Dict[str, Any]) -> Snapshot:
        return Snapshot(values={"messages": []})

    def _last_user_text(self, messages: list[Any]) -> str:
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                return message.content
            if isinstance(message, dict) and message.get("role") == "user":
                return message.get("content", "")
        return ""

    def _answer(self, text: str, customer_id: str) -> str:
        normalized = text.lower()
        if any(word in normalized for word in ["category", "categories", "分类"]):
            return self._categories_answer()
        if any(word in normalized for word in ["recommend", "推荐"]):
            return self._recommendations_answer(customer_id)
        if any(word in normalized for word in ["status", "track", "order", "订单", "物流"]):
            order_id = self._extract_order_id(normalized)
            return self._order_status_answer(customer_id, order_id)
        if any(word in normalized for word in ["stock", "price", "available", "product", "buy", "商品", "库存", "价格", "购买"]):
            return self._products_answer(normalized)
        return (
            "Local mock mode is running. You can ask about product categories, "
            "available products, prices, recommendations, or order status."
        )

    def _categories_answer(self) -> str:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT Category FROM products WHERE Quantity > 0 ORDER BY Category"
            ).fetchall()
        categories = ", ".join(row["Category"] for row in rows)
        return f"Available categories: {categories}."

    def _products_answer(self, text: str) -> str:
        query = self._extract_product_query(text)
        sql = "SELECT ProductName, Category, Price, Quantity FROM products WHERE Quantity > 0"
        params: list[Any] = []
        if query:
            sql += " AND LOWER(ProductName) LIKE ?"
            params.append(f"%{query}%")
        sql += " ORDER BY ProductName LIMIT 5"
        with db_manager.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        if not rows and query:
            return f"I could not find an in-stock product matching '{query}'."
        lines = [
            f"- {row['ProductName']} ({row['Category']}): ${row['Price']:.2f}, stock {row['Quantity']}"
            for row in rows
        ]
        return "Here are matching in-stock products:\n" + "\n".join(lines)

    def _order_status_answer(self, customer_id: str, order_id: Optional[str]) -> str:
        with db_manager.get_connection() as conn:
            if order_id:
                row = conn.execute(
                    """
                    SELECT o.OrderId, o.OrderDate, o.Status,
                           GROUP_CONCAT(p.ProductName || ' x' || od.Quantity) AS Products,
                           SUM(od.Quantity * od.UnitPrice) AS TotalAmount
                    FROM orders o
                    JOIN orders_details od ON o.OrderId = od.OrderId
                    JOIN products p ON od.ProductId = p.ProductId
                    WHERE o.OrderId = ? AND o.CustomerId = ?
                    GROUP BY o.OrderId
                    """,
                    (order_id, customer_id),
                ).fetchone()
                if not row:
                    return f"I could not find order #{order_id} for customer {customer_id}."
                return self._format_order(row)

            rows = conn.execute(
                """
                SELECT o.OrderId, o.OrderDate, o.Status,
                       COUNT(od.OrderDetailId) AS ItemCount,
                       SUM(od.Quantity * od.UnitPrice) AS TotalAmount
                FROM orders o
                JOIN orders_details od ON o.OrderId = od.OrderId
                WHERE o.CustomerId = ?
                GROUP BY o.OrderId
                ORDER BY o.OrderDate DESC
                """,
                (customer_id,),
            ).fetchall()
        if not rows:
            return (
                f"I do not see any orders for customer {customer_id}. "
                "This local demo starts with product data only; create an order in the full LLM mode or seed one for testing."
            )
        lines = [
            f"- Order #{row['OrderId']}: {row['Status']}, {row['ItemCount']} item(s), total ${row['TotalAmount']:.2f}"
            for row in rows
        ]
        return "Here are your recent orders:\n" + "\n".join(lines)

    def _recommendations_answer(self, customer_id: str) -> str:
        with db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT ProductName, Category, Price, Quantity
                FROM products
                WHERE Quantity > 0
                ORDER BY RANDOM()
                LIMIT 5
                """
            ).fetchall()
        lines = [
            f"- {row['ProductName']} ({row['Category']}): ${row['Price']:.2f}, stock {row['Quantity']}"
            for row in rows
        ]
        return f"Recommendations for customer {customer_id}:\n" + "\n".join(lines)

    def _format_order(self, row: Any) -> str:
        return (
            f"Order #{row['OrderId']} is {row['Status']}. "
            f"Products: {row['Products']}. "
            f"Order date: {row['OrderDate']}. "
            f"Total: ${row['TotalAmount']:.2f}."
        )

    def _extract_order_id(self, text: str) -> Optional[str]:
        match = re.search(r"(?:order\s*#?|订单\s*#?)(\d+)|#(\d+)", text)
        if not match:
            return None
        return next(group for group in match.groups() if group)

    def _extract_product_query(self, text: str) -> Optional[str]:
        known = [
            "gala apples",
            "ripe bananas",
            "navel oranges",
            "strawberries",
            "avocados",
            "red grapes",
            "blueberries",
            "lemons",
            "watermelon",
            "pineapple",
        ]
        for name in known:
            if name in text:
                return name
        return None


graph = LocalSalesGraph()
