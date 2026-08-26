"""Unit tests for the Chinese/Arabic numeral helpers used by ground matching
and the graph by-article queries."""

from cnlaw.ingest.cn_num import (arabic_to_cn, cn_num_to_int,
                                 cn_numerals_to_arabic, extract_article_number)


def test_cn_num_to_int():
    assert cn_num_to_int("十") == 10
    assert cn_num_to_int("二十") == 20
    assert cn_num_to_int("二十二") == 22
    assert cn_num_to_int("一百二十四") == 124
    assert cn_num_to_int("九十九") == 99


def test_cn_numerals_to_arabic():
    assert cn_numerals_to_arabic("第二十二条第三款") == "第22条第3款"
    assert cn_numerals_to_arabic("第九十九条第二款") == "第99条第2款"
    assert cn_numerals_to_arabic("第五条") == "第5条"


def test_arabic_to_cn():
    assert arabic_to_cn(5) == "五"
    assert arabic_to_cn(10) == "十"
    assert arabic_to_cn(20) == "二十"
    assert arabic_to_cn(22) == "二十二"
    assert arabic_to_cn(100) == "一百"
    assert arabic_to_cn(105) == "一百零五"
    assert arabic_to_cn(122) == "一百二十二"


def test_extract_article_number():
    assert extract_article_number("专利法第22条第3款") == 22
    assert extract_article_number("专利法第二十二条第三款") == 22
    assert extract_article_number("专利法实施细则第二十条") == 20
    assert extract_article_number("没有条号的引用") is None


def test_round_trip():
    for n in (1, 8, 10, 20, 22, 99, 100, 105, 122, 199):
        assert cn_num_to_int(arabic_to_cn(n)) == n
