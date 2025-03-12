import os
from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
import json
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Chave da API Deepseek
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-60c05941716344a4a5dbec3791286998")
DEEPSEEK_API_URL = "https://api.deepseek.com/beta/chat/completions"

def extract_text_from_url(url):
    """Extrai o texto de um URL do GZH"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Encontrar todos os parágrafos com a classe específica
        paragrafos = soup.find_all('div', class_='article-paragraph', attrs={'type': 'unstyled'})
        
        texto = []
        for p in paragrafos:
            p_tag = p.find('p')
            if p_tag:
                content = p_tag.get_text(strip=True)
                # Extrair apenas o conteúdo entre ###
                start = content.find('###')
                end = content.rfind('###')
                if start != -1 and end != -1 and start < end:
                    texto.append(content[start+3:end].strip())
                else:
                    texto.append(content)
        
        # Extrair título e subtítulo para contexto - usando os seletores específicos
        titulo = soup.find('h1', class_='mb-7 font-sans text-[32px] font-black leading-[34px] sm:text-[46px] sm:leading-[48px]')
        if not titulo:
            # Tenta um seletor alternativo se o primeiro não funcionar
            titulo = soup.find('h1')
        titulo = titulo.text.strip() if titulo else ''
        
        subtitulo = soup.find('p', class_='mb-5 font-plex text-[19px] leading-[25px] text-gzh-gray')
        if not subtitulo:
            # Tenta um seletor alternativo se o primeiro não funcionar
            subtitulo = soup.find('p', class_='font-plex')
        subtitulo = subtitulo.text.strip() if subtitulo else ''
        
        return {
            'titulo': titulo,
            'subtitulo': subtitulo,
            'texto': '\n\n'.join(texto)
        }
    except Exception as e:
        return {'error': str(e)}

def get_headlines_from_gzh():
    """Extrai as manchetes da página inicial do GZH"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get('https://gauchazh.clicrbs.com.br/', headers=headers, verify=False)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Buscar manchetes em diferentes seções usando os seletores específicos
        headlines = []
        
        # Seletores específicos fornecidos pelo usuário
        selectors = [
            "h3.text-lg.2xs\\:text-3xl.\\@xs\\:text-4xl.\\@md\\:text-3xl.\\@lg\\:text-4xl.font-black.text-black",
            "h3.text-lg.\\@xs\\:text-4xl.font-semibold.text-black",
            "h3.mb-3.font-plex.font-semibold.text-black",
            "h3.text-lg.\\@lg\\:text-3xl.\\@3xl\\:text-4xl.font-black.text-black"
        ]
        
        # Buscar por cada seletor específico
        for selector in selectors:
            try:
                # Para seletores com caracteres especiais, usamos find_all com attrs
                if '2xs:' in selector or '@' in selector:
                    # Extrair as classes do seletor
                    classes = selector.split('.')[1:]
                    # Encontrar elementos h3 com essas classes
                    elements = soup.find_all('h3', class_=lambda c: c and all(cls in c.split() for cls in classes if cls))
                else:
                    # Para seletores simples, podemos usar select
                    elements = soup.select(selector)
                
                for element in elements:
                    headline_link = element.find_parent('a')
                    if headline_link and 'href' in headline_link.attrs:
                        headlines.append({
                            'title': element.text.strip(),
                            'url': headline_link['href']
                        })
            except Exception as e:
                print(f"Erro ao processar seletor {selector}: {str(e)}")
        
        # Buscar também por h3 com classes que contenham as palavras-chave
        keywords = ["font-black", "font-semibold", "text-black"]
        h3_elements = soup.find_all('h3')
        for element in h3_elements:
            if element.get('class') and any(keyword in ' '.join(element.get('class', [])) for keyword in keywords):
                headline_link = element.find_parent('a')
                if headline_link and 'href' in headline_link.attrs:
                    # Verificar se já temos esta manchete
                    title = element.text.strip()
                    if not any(h['title'] == title for h in headlines):
                        headlines.append({
                            'title': title,
                            'url': headline_link['href']
                        })
        
        # Garantir URLs completas
        for headline in headlines:
            if not headline['url'].startswith('http'):
                headline['url'] = 'https://gauchazh.clicrbs.com.br' + headline['url']
        
        return headlines[:30]  # Retornar no máximo 30 manchetes
    except Exception as e:
        return {'error': str(e)}

def rewrite_for_radio(text_data):
    """Reescreve o texto para formato de rádio usando a API Deepseek"""
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }
        
        system_content = """
Você é um especialista em reescrever textos jornalísticos para serem lidos em rádio. Siga estas diretrizes RIGOROSAMENTE:

1. PRIORIZE as informações do TÍTULO e SUBTÍTULO da reportagem - estas são as informações mais importantes
2. Use ordem direta como prioridade (sujeito, verbo, predicado)
3. Use períodos curtos e simples
4. Use linguagem ativa e não passiva
5. Evite adjetivações
6. Evite cacofonia (sons desagradáveis quando palavras são pronunciadas juntas)
7. Identifique e mantenha APENAS as informações mais importantes
8. Limite o texto a NO MÁXIMO 10 linhas/frases
9. Termine CADA frase com "./" (ponto seguido de barra)
10. A última frase deve terminar com "///" (três barras)
11. Mantenha todos os nomes próprios e informações factuais exatamente como estão no original
12. Não invente informações que não estejam no texto original
13. Não use abreviações, exceto se já estiverem no texto original
14. Não use parênteses ou colchetes
15. Não use aspas, exceto para citações diretas essenciais
16. Não use reticências
17. Não use travessões
18. Não use pontos de exclamação
19. Não use pontos de interrogação, exceto em perguntas diretas essenciais
20. Não use siglas sem explicação, exceto as muito conhecidas (como ONU, EUA)
21. Comece o texto com "LOC - " (LOC espaço traço espaço)

REGRAS ESPECÍFICAS PARA DATAS E HORÁRIOS:
22. Ao mencionar datas, NUNCA inclua o dia do mês. Por exemplo, use "neste domingo" em vez de "neste domingo, dia 8 de julho"
23. Ao mencionar horários, SEMPRE use o formato de 12 horas com "da manhã", "da tarde" ou "da noite". Por exemplo:
    - Use "5 da tarde" em vez de "17 horas" ou "17h"
    - Use "4 e 15 da tarde" em vez de "16h15min" ou "16:15"
    - Use "10 da manhã" em vez de "10 horas" ou "10h"
    - Use "8 e meia da noite" em vez de "20h30min" ou "20:30"

Exemplo de formato correto:
LOC - A Trensurb vai reduzir o intervalo entre as viagens de 12 para 10 minutos no início da manhã e no final da tarde a partir de segunda-feira./ Segundo a empresa, a redução ocorrerá das 7 e 15 da manhã às 8 e 15 da manhã, e das 5 e 15 da tarde às 6 e 15 da tarde, no sentido Mercado - Novo Hamburgo./ Já na direção oposta, o tempo de espera será menor, entre 6 e meia e 7 e meia da manhã, e das 4 e 15 às 5 e 15 da tarde./ A diminuição foi possível devido ao avanço das obras de recuperação das estruturas atingidas pela enchente.///
"""
      
        user_content = f"""
Reescreva o seguinte texto jornalístico para ser lido em rádio, seguindo ESTRITAMENTE as diretrizes fornecidas.
PRIORIZE as informações do TÍTULO e SUBTÍTULO - estas são as informações mais importantes e DEVEM ser incluídas no texto reescrito:

TÍTULO: {text_data['titulo']}

SUBTÍTULO: {text_data['subtitulo']}

Texto complementar:
{text_data['texto']}
"""
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ]
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        rewritten_text = result['choices'][0]['message']['content']
        
        return {'rewritten_text': rewritten_text}
    except Exception as e:
        return {'error': str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def extract():
    data = request.get_json()
    url = data.get('url', '')
    
    if not url:
        return jsonify({'error': 'URL não fornecido'})
    
    result = extract_text_from_url(url)
    return jsonify(result)

@app.route('/rewrite', methods=['POST'])
def rewrite():
    data = request.get_json()
    text = data.get('text', '')
    
    if not text:
        return jsonify({'error': 'Texto não fornecido'})
    
    # Se o texto for fornecido diretamente (não de uma URL)
    text_data = {
        'titulo': data.get('titulo', ''),
        'subtitulo': data.get('subtitulo', ''),
        'texto': text
    }
    
    result = rewrite_for_radio(text_data)
    return jsonify(result)

@app.route('/process_url', methods=['POST'])
def process_url():
    data = request.get_json()
    url = data.get('url', '')
    
    if not url:
        return jsonify({'error': 'URL não fornecido'})
    
    # Extrair o texto do URL
    extracted = extract_text_from_url(url)
    
    if 'error' in extracted:
        return jsonify(extracted)
    
    # Reescrever o texto extraído
    result = rewrite_for_radio(extracted)
    
    # Combinar os resultados
    response = {
        'extracted': extracted,
        'rewritten': result.get('rewritten_text', ''),
        'error': result.get('error', None)
    }
    
    return jsonify(response)

@app.route('/get_headlines', methods=['GET'])
def get_headlines():
    """Endpoint para obter manchetes do GZH"""
    headlines = get_headlines_from_gzh()
    return jsonify(headlines)

if __name__ == '__main__':
    # Use a porta fornecida pelo ambiente ou 5000 como padrão
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

