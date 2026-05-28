"""TWSE OpenAPI MCP Server - 台灣證券交易所股市資料"""

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("twse")
BASE = "https://openapi.twse.com.tw/v1"


async def _get(path: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{BASE}/{path}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def stock_day_all() -> str:
    """取得所有上市個股當日成交資訊（代號、名稱、成交股數、成交金額、開盤、最高、最低、收盤、漲跌、本益比）"""
    data = await _get("exchangeReport/STOCK_DAY_ALL")
    lines = [f"{d['Code']} {d['Name']} 收:{d['ClosingPrice']} 漲跌:{d['Change']} 量:{d['TradeVolume']}" for d in data[:50]]
    return f"共 {len(data)} 檔，前50:\n" + "\n".join(lines)


@mcp.tool()
async def stock_price(symbol: str) -> str:
    """查詢特定股票代號的當日成交資訊（如 2330 台積電）"""
    data = await _get("exchangeReport/STOCK_DAY_ALL")
    for d in data:
        if d["Code"] == symbol:
            return (
                f"{d['Code']} {d['Name']}\n"
                f"開盤: {d['OpeningPrice']} | 最高: {d['HighestPrice']} | 最低: {d['LowestPrice']}\n"
                f"收盤: {d['ClosingPrice']} | 漲跌: {d['Change']}\n"
                f"成交股數: {d['TradeVolume']} | 成交金額: {d['TradeValue']}\n"
                f"成交筆數: {d['Transaction']}"
            )
    return f"找不到股票代號 {symbol}"


@mcp.tool()
async def market_index() -> str:
    """取得大盤統計資訊（加權指數等）"""
    data = await _get("exchangeReport/MI_INDEX")
    lines = [f"{d['指數']} {d['收盤指數']} 漲跌:{d['漲跌點數']}({d['漲跌百分比']}%)" for d in data if d.get("收盤指數")]
    return "\n".join(lines) if lines else "無資料（可能非交易日）"


@mcp.tool()
async def top20_volume() -> str:
    """取得當日成交量前20名證券"""
    data = await _get("exchangeReport/MI_INDEX20")
    lines = [f"{d['Code']} {d['Name']} 成交量:{d['TradeVolume']} 收盤:{d['ClosingPrice']}" for d in data]
    return "\n".join(lines) if lines else "無資料"


@mcp.tool()
async def foreign_holding() -> str:
    """取得外資及陸資持股前20名"""
    data = await _get("fund/MI_QFIIS_sort_20")
    lines = [f"{d.get('證券代號','')} {d.get('證券名稱','')} 持股:{d.get('全體外資及陸資持股數','')}" for d in data]
    return "\n".join(lines) if lines else "無資料"


@mcp.tool()
async def margin_trading() -> str:
    """取得集中市場融資融券餘額（前30檔）"""
    data = await _get("exchangeReport/MI_MARGN")
    lines = [f"{d.get('股票代號','')} {d.get('股票名稱','')} 融資餘額:{d.get('融資今日餘額','')} 融券餘額:{d.get('融券今日餘額','')}" for d in data[:30]]
    return "\n".join(lines) if lines else "無資料"


@mcp.tool()
async def pe_ratio(symbol: str) -> str:
    """查詢特定股票的本益比、殖利率、股價淨值比"""
    data = await _get("exchangeReport/BWIBBU_ALL")
    for d in data:
        if d.get("Code") == symbol:
            return (
                f"{d['Code']} {d['Name']}\n"
                f"本益比: {d.get('PEratio', 'N/A')}\n"
                f"殖利率: {d.get('DividendYield', 'N/A')}%\n"
                f"股價淨值比: {d.get('PBratio', 'N/A')}"
            )
    return f"找不到股票代號 {symbol}"


@mcp.tool()
async def holiday_schedule() -> str:
    """取得證券市場開休市日期"""
    data = await _get("holidaySchedule/holidaySchedule")
    lines = [f"{d.get('Date','')} {d.get('Name','')} ({d.get('Description','')})" for d in data[:20]]
    return "\n".join(lines) if lines else "無資料"


if __name__ == "__main__":
    mcp.run(transport="stdio")