"""有 Bug 的计算器 — 用于测试 AutoLoop"""

def add(a, b):
    """加法 — BUG: 不处理负数"""
    if a < 0 or b < 0:
        return 0  # 错误：负数应该正常相加
    return a + b


def subtract(a, b):
    """减法 — 正常"""
    return a - b


def multiply(a, b):
    """乘法 — BUG: 用递归实现，大数会栈溢出"""
    if b == 0:
        return 0
    if b < 0:
        return -multiply(a, -b)
    return a + multiply(a, b - 1)


def divide(a, b):
    """除法 — BUG: 没有处理除零"""
    return a / b


def power(base, exp):
    """幂运算 — BUG: exp=0 时返回 0 而不是 1"""
    if exp == 0:
        return 0
    if exp == 1:
        return base
    return base * power(base, exp - 1)
