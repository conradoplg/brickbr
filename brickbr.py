import traceback
from datetime import datetime
import csv
from collections import namedtuple
import decimal

from bs4 import BeautifulSoup
from price_parser import Price
import simplejson as json
from jinja2 import Template

import requests
import requests_cache

requests_cache.install_cache()

SetPrice = Point = namedtuple('SetPrice', ['set', 'price', 'name', 'date', 'url'])


def get_brickset_price(url, set_number):
    html = requests.get(url).content
    soup = BeautifulSoup(html, 'html.parser')
    dt_tag = soup.find('dt', string='RRP')
    dd_tag = dt_tag.find_next_sibling('dd')
    h1_tag = soup.select_one('header > h1')
    name = str(h1_tag.string.strip())
    if dd_tag:
        usd_str = [currency_str for currency_str in dd_tag.string.split(' / ') if '$' in currency_str]
        if not usd_str:
            return None
        usd = Price.fromstring(usd_str[0]).amount
        return SetPrice(set=str(set_number), price=usd, name=name, date=datetime.utcnow().isoformat(), url=url)


def get_legobrasil_price(url):
    html = requests.get(url).content
    soup = BeautifulSoup(html, 'html.parser')
    price_tag = soup.find(class_='skuBestPrice')
    set_tag = soup.find(class_='productDescriptionShort')
    name_tag = soup.find(class_='productName')
    if set_tag is None or price_tag is None:
        return None
    price = Price.fromstring(price_tag.string.strip()).amount
    name = str(name_tag.string.strip())
    return SetPrice(set=str(set_tag.string), price=price, name=name, date=datetime.utcnow().isoformat(), url=url)


def update_prices():
    html = requests.get("https://www.legobrasil.com.br/sitemap/sitemap-products-1.xml").content
    soup = BeautifulSoup(html, 'html.parser')
    url_tag_lst = soup('url')

    usd_map = {}
    brl_map = {}

    for url_tag in url_tag_lst:
        try:
            url = url_tag.loc.string.strip()
            print(url)
            brl_set_price = get_legobrasil_price(url)
            print(brl_set_price)
            if brl_set_price:
                brl_map[brl_set_price.set] = brl_set_price
                bs_url = f'https://brickset.com/sets/{brl_set_price.set}-1/'
                usd_set_price = get_brickset_price(bs_url, brl_set_price.set)
                if usd_set_price:
                    usd_map[usd_set_price.set] = usd_set_price
                    print(usd_set_price)
        except KeyboardInterrupt:
            break
        except:
            traceback.print_exc()
    with open('brl.json', 'w') as f:
        json.dump(brl_map, f, indent='\t')
    with open('usd.json', 'w') as f:
        json.dump(usd_map, f, indent='\t')


def generate_output(brl_fn, usd_fn):
    usd_map = {}
    brl_map = {}
    with open(brl_fn, 'r') as f:
        brl_map = json.load(f)
    with open(usd_fn, 'r') as f:
        usd_map = json.load(f)

    csv_lst = []
    json_lst = []
    for set, bsp in brl_map.items():
        bsp = SetPrice(**bsp)
        usp = usd_map.get(set, None)
        if usp:
            usp = SetPrice(**usp)
            ratio = (decimal.Decimal(bsp.price) / decimal.Decimal(usp.price)).quantize(decimal.Decimal('0.01'))
            csv_lst.append((set, usp.name, usp.price, bsp.price, ratio, bsp.url))
            json_lst.append(dict(name=usp.name, usd=usp.price, brl=bsp.price, ratio=ratio,
                                 brl_url=bsp.url))

    csv_lst.sort(key=lambda x: x[4])
    json_lst.sort(key=lambda x: x['ratio'])

    with open('prices.csv', 'w') as f:
        w = csv.writer(f)
        w.writerows(csv_lst)

    with open('template.html', 'r') as f:
        rendered = Template(f.read()).render(item_list=json_lst)
        with open('index.html', 'w') as w:
            w.write(rendered)


if __name__ == "__main__":
    # update_prices()
    generate_output('brl.json', 'usd.json')
