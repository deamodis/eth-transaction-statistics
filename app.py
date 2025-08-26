# app.py
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal

from eth_stats import compute_address_stats

app = FastAPI(title="ETH Tx Stats (fixed EUR)")

class StatsResponse(BaseModel):
    params: dict
    eth: dict
    stablecoins: dict
    unified: dict

@app.get("/address/{address}", response_model=StatsResponse)
def get_stats(
    address: str,
    include_internal: bool = Query(False),
    include_tokens: bool = Query(False),
    exclude_zero_eth: bool = Query(False),
    unified: bool = Query(False),
    startblock: int = Query(0, ge=0),
    endblock: int = Query(99_999_999, ge=0),
    sort: Literal["asc", "desc"] = Query("asc"),
):
    try:
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
