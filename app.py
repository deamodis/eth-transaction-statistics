# app.py
from fastapi import FastAPI, Query, Depends
from pydantic import BaseModel
from typing import Literal
from sqlalchemy.ext.asyncio import AsyncSession
from db import SessionLocal, AddressQuery

from eth_stats import compute_address_stats

app = FastAPI(title="ETH Tx Stats (fixed EUR)")

class StatsResponse(BaseModel):
    stablecoins: dict

async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

@app.get("/address/{address}", response_model=StatsResponse)
async def get_stats(
    address: str,
    include_internal: bool = Query(False),
    include_tokens: bool = Query(True),
    exclude_zero_eth: bool = Query(False),
    unified: bool = Query(False),
    startblock: int = Query(0, ge=0),
    endblock: int = Query(99_999_999, ge=0),
    sort: Literal["asc", "desc"] = Query("asc"),
    session: AsyncSession = Depends(get_session),
):
    session.add(AddressQuery(address=address))
    await session.commit()

    result = compute_address_stats(
        address,
        include_internal=include_internal,
        include_tokens=include_tokens,
        exclude_zero_eth=exclude_zero_eth,
        unified=unified,
        startblock=startblock,
        endblock=endblock,
        sort=sort,
    )
    return result
