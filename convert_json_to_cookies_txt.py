import json

with open('cookies.json', 'r', encoding='utf-8') as f:
    cookies = json.load(f)

with open('cookies.txt', 'w', encoding='utf-8') as f:
    f.write('# Netscape HTTP Cookie File\n\n')
    for cookie in cookies:
        domain = cookie['domain']
        include_subdomain = 'TRUE' if domain.startswith('.') else 'FALSE'
        path = cookie['path']
        secure = 'TRUE' if cookie['secure'] else 'FALSE'
        expiration = int(cookie['expirationDate']) if 'expirationDate' in cookie else 0
        name = cookie['name']
        value = cookie['value']
        f.write(f'{domain}\t{include_subdomain}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n')
