"""calculator.py 的测试用例"""

import pytest
from calculator import add, subtract, multiply, divide, power


class TestAdd:
    def test_positive_numbers(self):
        assert add(2, 3) == 5

    def test_zero(self):
        assert add(0, 0) == 0

    def test_negative_numbers(self):
        assert add(-1, -2) == -3

    def test_mixed_sign(self):
        assert add(-1, 5) == 4

    def test_large_numbers(self):
        assert add(1000000, 2000000) == 3000000


class TestSubtract:
    def test_basic(self):
        assert subtract(5, 3) == 2

    def test_negative_result(self):
        assert subtract(3, 5) == -2


class TestMultiply:
    def test_basic(self):
        assert multiply(3, 4) == 12

    def test_zero(self):
        assert multiply(5, 0) == 0

    def test_negative(self):
        assert multiply(-3, 4) == -12

    def test_large_number(self):
        assert multiply(100, 100) == 10000


class TestDivide:
    def test_basic(self):
        assert divide(10, 2) == 5.0

    def test_division_by_zero(self):
        with pytest.raises(ZeroDivisionError):
            divide(10, 0)

    def test_negative(self):
        assert divide(-10, 2) == -5.0


class TestPower:
    def test_basic(self):
        assert power(2, 3) == 8

    def test_zero_exponent(self):
        assert power(5, 0) == 1

    def test_one_exponent(self):
        assert power(7, 1) == 7
