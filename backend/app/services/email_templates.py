"""HTML e-mail templates with plain-text fallbacks."""

from __future__ import annotations


def password_reset_code_email(
    *, code: str, expire_minutes: int, app_name: str
) -> dict[str, str]:
    subject = f"{app_name} — código de redefinição de senha"
    text = (
        "Recebemos um pedido para redefinir sua senha.\n\n"
        f"Seu código de verificação é: {code}\n\n"
        f"Ele é válido por {expire_minutes} minutos e só pode ser usado uma vez.\n"
        "Se não foi você, ignore este e-mail — sua senha continua a mesma."
    )
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{app_name}</title>
</head>
<body style="margin:0;padding:0;background:#0b0910;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">Seu código de redefinição de senha do {app_name}.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b0910;padding:32px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#171420;border:1px solid #2a2438;border-radius:20px;overflow:hidden;">
<tr><td style="padding:28px 32px 0 32px;">
<div style="font-family:'Segoe UI',Arial,sans-serif;font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#f2a33c;font-weight:700;">{app_name}</div>
</td></tr>
<tr><td style="padding:16px 32px 0 32px;font-family:'Segoe UI',Arial,sans-serif;">
<h1 style="margin:0;font-size:24px;line-height:1.25;color:#efeaf7;">Redefinição de senha</h1>
<p style="margin:14px 0 0 0;font-size:15px;line-height:1.6;color:#b9b2c8;">Recebemos um pedido para redefinir a senha da sua conta. Use o código abaixo no site para criar uma nova senha.</p>
</td></tr>
<tr><td style="padding:26px 32px 0 32px;">
<div style="background:#1d1928;border:1px solid #2a2438;border-radius:14px;padding:22px 12px;text-align:center;font-family:'IBM Plex Mono','Courier New',monospace;font-size:34px;line-height:1;letter-spacing:10px;font-weight:700;color:#f2a33c;">{code}</div>
</td></tr>
<tr><td style="padding:18px 32px 0 32px;font-family:'Segoe UI',Arial,sans-serif;font-size:13px;line-height:1.6;color:#8b8399;">
Este código é válido por <strong style="color:#efeaf7;">{expire_minutes} minutos</strong>. Se não foi você, ignore este e-mail — sua senha continua a mesma.
</td></tr>
<tr><td style="padding:18px 32px 28px 32px;font-family:'Segoe UI',Arial,sans-serif;font-size:12px;line-height:1.6;color:#6f6880;">
Por segurança, este código expira automaticamente e só pode ser usado uma vez.
</td></tr>
</table>
<p style="margin:18px 0 0 0;font-family:'Segoe UI',Arial,sans-serif;font-size:11px;color:#4f4a5e;">&copy; {app_name}</p>
</td></tr>
</table>
</body>
</html>"""
    return {"subject": subject, "text": text, "html": html}
