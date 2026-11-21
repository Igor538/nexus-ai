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
    _transparent_cell = (
        "style=\"display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;\""
    )
    _table_bg = "style=\"background:#0b0910;padding:32px 12px;\""
    _inner_table = (
        "style=\"max-width:560px;background:#171420;border:1px solid #2a2438;"
        "border-radius:20px;overflow:hidden;\""
    )
    _app_name_style = (
        "style=\"font-family:'Segoe UI',Arial,sans-serif;font-size:12px;"
        "letter-spacing:2px;text-transform:uppercase;color:#f2a33c;font-weight:700;\""
    )
    _header_style = (
        "style=\"padding:28px 32px 0 32px;font-family:'Segoe UI',Arial,sans-serif;"
        "font-size:24px;line-height:1.25;color:#efeaf7;\""
    )
    _paragraph_style = (
        "style=\"padding:16px 32px 0 32px;font-family:'Segoe UI',Arial,sans-serif;"
        "font-size:15px;line-height:1.6;color:#b9b2c8;\""
    )
    _code_box_style = (
        "style=\"padding:26px 32px 0 32px;background:#1d1928;border:1px solid #2a2438;"
        "border-radius:14px;padding:22px 12px;text-align:center;font-family:'IBM Plex Mono',"
        "'Courier New',monospace;font-size:34px;line-height:1;letter-spacing:10px;"
        "font-weight:700;color:#f2a33c;\""
    )
    _text_style = (
        "style=\"padding:18px 32px 0 32px;font-family:'Segoe UI',Arial,sans-serif;"
        "font-size:13px;line-height:1.6;color:#8b8399;\""
    )
    _footer_style = (
        "style=\"padding:18px 32px 28px 32px;font-family:'Segoe UI',Arial,sans-serif;"
        "font-size:12px;line-height:1.6;color:#6f6880;\""
    )
    _reset_text = "Recebemos um pedido para redefinir a senha da sua conta. Use o código abaixo no site para criar uma nova senha."  # noqa: E501
    _expire_text = "Este código é válido por {expire_minutes} minutos. Se não foi você, ignore este e-mail — sua senha continua a mesma."  # noqa: E501
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{app_name}</title>
</head>
<body style="margin:0;padding:0;background:#0b0910;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" {_table_bg}>
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" {_inner_table}>
<tr><td align="center">
{_transparent_cell}Seu código de redefinição de senha do {app_name}.</td></tr>
<tr><td>
<div {_app_name_style}>{app_name}</div>
</td></tr>
<tr><td {_header_style}><h1>Redefinição de senha</h1>
<p {_paragraph_style}>{_reset_text}</p>
</td></tr>
<tr><td {_code_box_style}>{code}</div>
</td></tr>
<tr><td {_text_style}>_expire_text</p>
</td></tr>
</table>
<p {_footer_style}&copy; {app_name}</p>
</td></tr>
</table>
</body>
</html>"""
    return {"subject": subject, "text": text, "html": html}