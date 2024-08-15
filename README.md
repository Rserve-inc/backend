## 飲食店向けダッシュボードのバックエンド

[フロントエンド](https://github.com/Rserve-inc/business-dashboard)

## 認証

JWTを利用し、httpOnly cookieに保存しています。  
access tokenの有効期限は15分、refresh tokenの有効期限は30日です。

## サブモジュールの扱い

このリポジトリはgitサブモジュールとして、フロントエンドの`deploy`ブランチを含んでいます。  
クローンする際は **`git clone --recursive <repo_url>`を使用して、サブモジュールも含めてください。**
