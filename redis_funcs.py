import redis

import envs

# Redisクライアントの設定
redis_client = redis.Redis(host=envs.REDIS_HOST, port=6379, db=0)


# フラグのセット
def set_update_flag(restaurant_id: str):
    redis_client.set(f"update_flag:{restaurant_id}", "1")


# フラグのチェック
def check_for_updates(restaurant_id: str) -> bool:
    if redis_client.get(f"update_flag:{restaurant_id}") == b"1":
        redis_client.delete(f"update_flag:{restaurant_id}")
        return True
    return False
