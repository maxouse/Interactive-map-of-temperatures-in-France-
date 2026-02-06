# -*- coding: utf-8 -*-
"""

@author: Projet WEB F, groupe A1a 2025
"""

import http.server
import socketserver
from urllib.parse import urlparse, parse_qs, unquote
import json

import datetime as dt
import os
import sqlite3

import matplotlib.pyplot as plt
import matplotlib.dates as pltd

import threading
import io
import sys

# numéro du port TCP utilisé par le serveur
port_serveur = 8080
# nom de la base de données
BD_name = "DB_Temp.sqlite"

FORUM_FILE = "forum.json"
forum_lock = threading.Lock()

def read_forum():
    if not os.path.exists(FORUM_FILE):
        return []
    with open(FORUM_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []

def write_forum(data):
    with forum_lock:
        with open(FORUM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

class RequestHandler(http.server.SimpleHTTPRequestHandler):
  """"Classe dérivée pour traiter les requêtes entrantes du serveur"""

  # sous-répertoire racine des documents statiques
  static_dir = 'client'
  
  def __init__(self, *args, **kwargs):
    """Surcharge du constructeur pour imposer 'client' comme sous répertoire racine"""

    super().__init__(*args, directory=self.static_dir, **kwargs)
    

  def do_GET(self):
    """Traiter les requêtes GET (surcharge la méthode héritée)"""

    # On récupère les étapes du chemin d'accès
    self.init_params()

    # Nouvelle API REST
    if self.path_info[0] == 'api':
      if len(self.path_info) > 1:
        if self.path_info[1] == 'stations':
          self.send_stations()
        elif self.path_info[1] == 'temperatures':
          self.send_temperatures_json()
        elif self.path_info[1] == 'has_min':
          self.send_has_min()
        elif self.path_info[1] == 'forum':
          self.send_forum()
        else:
          self.send_error(404)
      else:
        self.send_error(404)
      return

    # Anciennes routes (pour compatibilité)
    if self.path_info[0] == 'stations':
      self.send_stations()
    elif self.path_info[0] == 'temperature':
      self.send_temperature()
    else:
      super().do_GET()


  def send_stations(self):
    """Génèrer une réponse avec la liste des stations et leur info has_min et has_max"""
    c = conn.cursor()
    c.execute("SELECT num_serie, nom_usuel, latitude, longitude, altitude FROM stations_TN UNION SELECT num_serie, nom_usuel, latitude,longitude, altitude FROM stations_TX")
    stations = c.fetchall()
    result = []
    for (num_serie, nom_usuel, latitude, longitude, altitude) in stations:
        # Pour temp_min
        station_id_min = num_serie
        if num_serie.startswith('MTX'):
            station_id_min = 'MTN' + num_serie[3:]
        elif num_serie.startswith('STX'):
            station_id_min = 'STN' + num_serie[3:]
        c.execute("SELECT 1 FROM temp_min WHERE num_serie = ? LIMIT 1", (station_id_min,))
        has_min = c.fetchone() is not None
        # Pour temp_max
        c.execute("SELECT 1 FROM temp_max WHERE num_serie = ? LIMIT 1", (num_serie,))
        has_max = c.fetchone() is not None
        result.append({
            'num': num_serie,
            'nom': nom_usuel,
            'lat': latitude,
            'lon': longitude,
            'alt': altitude,
            'has_min': has_min,
            'has_max': has_max
        })
    body = json.dumps(result)
    headers = [('Content-Type','application/json')]
    self.send(body, headers)


  def send_temperature(self):
    """Retourner une réponse faisant référence au graphique de temperature"""

    # création du curseur (la connexion a été créée par le programme principal)
    c = conn.cursor()

    # si pas de paramètre => erreur pas de région
    if len(self.path_info) <= 1 or self.path_info[1] == '' :
        # Région non spécifiée -> erreur 400 Bad Request
        print ('Erreur pas de nom')
        self.send_error(400)
        return None
    
    
    
    else:
        # on récupère le numéro de la station dans le 1er paramètre
        station = self.path_info[1]
    
    # Test de la présence du fichier dans le cache
    URL_graphique = 'courbes/temperature_{}.png'.format(station)
    fichier = self.static_dir + '/{}'.format(URL_graphique)
    if not os.path.exists(fichier):
        print('creer_graphique : ', station)
        self.creer_graphique (station, fichier)
    
    # réponse au format JSON
    body = json.dumps({
            'title': 'Température  {}'.format(station), \
            'img': '/{}'.format(URL_graphique) \
             });
     
    # envoi de la réponse
    headers = [('Content-Type','application/json')];
    self.send(body,headers)


  def creer_graphique(self, station, nom_fichier):
    """Générer un graphique des températures min et max et l'enregistrer dans le cache"""

    c = conn.cursor()

    # configuration du tracé
    plt.figure(figsize=(18,6))
    plt.grid(which='major', color='#888888', linestyle='-')
    plt.grid(which='minor', axis='x', color='#888888', linestyle=':')

    ax = plt.subplot(111)
    loc_major = pltd.YearLocator()
    loc_minor = pltd.MonthLocator()
    ax.xaxis.set_major_locator(loc_major)
    ax.xaxis.set_minor_locator(loc_minor)
    format_major = pltd.DateFormatter('%B %Y')
    ax.xaxis.set_major_formatter(format_major)
    ax.xaxis.set_tick_params(labelsize=10)

    # Récupération des températures max
    c.execute("SELECT Date, Valeur FROM temp_max WHERE num_serie = ? AND substr(Date,1,4) = ? ORDER BY Date", (station, str(dt.datetime.now().year)))
    r_tx = c.fetchall()
    x_tx = [pltd.date2num(dt.datetime.strptime(a[0], "%Y-%m-%d").date()) for a in r_tx if a[1] is not None]
    y_tx = [float(a[1]) for a in r_tx if a[1] is not None]
    plt.plot_date(x_tx, y_tx, '-', color='red', label='Temp. Max')

    # Récupération des températures min
    station_id_min = station
    if station.startswith('MTX'):
        station_id_min = 'MTN' + station[3:]
    elif station.startswith('STX'):
        station_id_min = 'STN' + station[3:]
    c.execute("SELECT Date, Valeur FROM temp_min WHERE num_serie = ? AND substr(Date,1,4) = ? ORDER BY Date", (station_id_min, str(dt.datetime.now().year)))
    r_tn = c.fetchall()
    x_tn = [pltd.date2num(dt.datetime.strptime(a[0], "%Y-%m-%d").date()) for a in r_tn if a[1] is not None]
    y_tn = [float(a[1]) for a in r_tn if a[1] is not None]
    plt.plot_date(x_tn, y_tn, '-', color='blue', label='Temp. Min')

    # légendes
    plt.legend(loc='upper left')
    plt.title(f'Températures min et max pour la station {station}', fontsize=16)
    plt.ylabel('Température (°C)')
    plt.xlabel('Date')

    # enregistrement
    plt.savefig(nom_fichier)
    plt.close()

    

  def send(self, body, headers=[]):
    """Envoyer la réponse au client avec le corps et les en-têtes fournis
    
    Arguments:
    body: corps de la réponse
    headers: liste de tuples d'en-têtes Cf. HTTP (par défaut : liste vide)
    """
    # on encode la chaine de caractères à envoyer
    encoded = bytes(body, 'UTF-8')

    # on envoie la ligne de statut
    self.send_response(200)

    # on envoie les lignes d'entête et la ligne vide
    [self.send_header(*t) for t in headers]
    self.send_header('Content-Length', int(len(encoded)))
    self.end_headers()

    # on envoie le corps de la réponse
    self.wfile.write(encoded)


  def init_params(self):
    """Analyse la requête pour initialiser nos paramètres"""

    # analyse de l'adresse
    info = urlparse(self.path)
    self.path_info = [unquote(v) for v in info.path.split('/')[1:]]
    self.query_string = info.query
    
    # récupération des paramètres dans la query string
    self.params = parse_qs(info.query)

    # récupération du corps et des paramètres (2 encodages traités)
    length = self.headers.get('Content-Length')
    ctype = self.headers.get('Content-Type')
    if length:
      self.body = str(self.rfile.read(int(length)),'utf-8')
      if ctype and ctype.startswith('application/x-www-form-urlencoded'):
        self.params = parse_qs(self.body)
      elif ctype and ctype.startswith('application/json'):
        self.params = json.loads(self.body)
    else:
      self.body = ''

    # traces
    print('init_params|info_path =', self.path_info)
    print('init_params|body =', length, ctype, self.body)
    print('init_params|params =', self.params)


  def send_temperatures_json(self):
    """Retourner les températures min et max pour une station et une période sous forme JSON"""
    c = conn.cursor()
    params = self.params
    station_id = params.get('station_id', [None])[0]
    start = params.get('start', [None])[0]
    end = params.get('end', [None])[0]
    if not station_id or not start or not end:
      self.send_error(400, 'station_id, start and end are required')
      return
    # Températures max
    c.execute("SELECT YYYYMM, Valeur FROM temp_max WHERE num_serie = ? AND YYYYMM >= ? AND YYYYMM <= ? ORDER BY YYYYMM", (station_id, start, end))
    r_tx = c.fetchall()
    # Températures min
    station_id_min = station_id
    if station_id.startswith('MTX'):
        station_id_min = 'MTN' + station_id[3:]
    elif station_id.startswith('STX'):
        station_id_min = 'STN' + station_id[3:]
    c.execute("SELECT YYYYMM, VALEUR FROM temp_min WHERE num_serie = ? AND YYYYMM >= ? AND YYYYMM <= ? ORDER BY YYYYMM", (station_id_min, start, end))
    r_tn = c.fetchall()
    # Formatage (dates en chaînes)
    data = {
      'max': [{'date': str(a[0]), 'value': a[1]} for a in r_tx if a[1] is not None],
      'min': [{'date': str(a[0]), 'value': a[1]} for a in r_tn if a[1] is not None]
    }
    body = json.dumps(data)
    print("Réponse JSON envoyée :", body)  # Ajout du print pour le debug
    headers = [('Content-Type','application/json')]
    self.send(body, headers)


  def send_has_min(self):
    """Répond true/false si la station a des températures min"""
    c = conn.cursor()
    params = self.params
    station_id = params.get('station_id', [None])[0]
    if not station_id:
      self.send_error(400, 'station_id is required')
      return
    num_serie_min = station_id
    if station_id.startswith('MTX'):
      num_serie_min = 'MTN' + station_id[3:]
    elif station_id.startswith('STX'):
      num_serie_min = 'STN' + station_id[3:]
    c.execute("SELECT 1 FROM temp_min WHERE num_serie = ? LIMIT 1", (num_serie_min,))
    has_min = c.fetchone() is not None
    body = json.dumps({'has_min': has_min})
    headers = [('Content-Type','application/json')]
    self.send(body, headers)


  def send_forum(self):
    forum = read_forum()
    body = json.dumps(forum)
    headers = [('Content-Type','application/json')]
    self.send(body, headers)


  def do_POST(self):
    self.init_params()
    if self.path_info[0] == 'api':
      if len(self.path_info) > 1:
        if self.path_info[1] == 'forum':
          if len(self.path_info) == 2:
            self.post_forum()
            return
          elif len(self.path_info) > 2 and self.path_info[2] == 'reply':
            self.post_forum_reply()
            return
          elif len(self.path_info) > 2 and self.path_info[2] == 'delete':
            self.post_forum_delete()
            return
          elif len(self.path_info) > 2 and self.path_info[2] == 'edit':
            self.post_forum_edit()
            return
      self.send_error(404)


  def post_forum(self):
    params = self.params
    author = params.get('author', [''])[0].strip()
    content = params.get('content', [''])[0].strip()
    if not author or not content:
      self.send_error(400, 'author and content required')
      return
    forum = read_forum()
    new_id = 1 + max([m.get('id', 0) for m in forum] or [0])
    msg = {'id': new_id, 'author': author, 'content': content, 'replies': []}
    forum.append(msg)
    write_forum(forum)
    self.send(json.dumps({'ok': True, 'id': new_id}), [('Content-Type','application/json')])


  def post_forum_reply(self):
    params = self.params
    try:
      msg_id = int(params.get('id', [''])[0])
    except Exception:
      self.send_error(400, 'id required')
      return
    author = params.get('author', [''])[0].strip()
    content = params.get('content', [''])[0].strip()
    if not author or not content:
      self.send_error(400, 'author and content required')
      return
    forum = read_forum()
    for msg in forum:
      if msg.get('id') == msg_id:
        msg.setdefault('replies', []).append({'author': author, 'content': content})
        write_forum(forum)
        self.send(json.dumps({'ok': True}), [('Content-Type','application/json')])
        return
    self.send_error(404, 'message not found')


  def post_forum_delete(self):
    params = self.params
    try:
      msg_id = int(params.get('id', [''])[0])
    except Exception:
      self.send_error(400, 'id required')
      return
    author = params.get('author', [''])[0].strip()
    reply_idx = params.get('reply_idx', [None])[0]
    forum = read_forum()
    changed = False
    if reply_idx is not None:
      # Suppression d'une réponse
      try:
        reply_idx = int(reply_idx)
      except Exception:
        self.send_error(400, 'reply_idx must be int')
        return
      for msg in forum:
        if msg.get('id') == msg_id:
          if 0 <= reply_idx < len(msg.get('replies', [])):
            if msg['replies'][reply_idx]['author'] == author:
              del msg['replies'][reply_idx]
              changed = True
              break
            else:
              self.send_error(403, 'author mismatch')
              return
      if changed:
        write_forum(forum)
        self.send(json.dumps({'ok': True}), [('Content-Type','application/json')])
        return
      self.send_error(404, 'reply not found')
      return
    # Suppression d'un message principal
    for i, msg in enumerate(forum):
      if msg.get('id') == msg_id:
        if msg.get('author') == author:
          del forum[i]
          changed = True
          break
        else:
          self.send_error(403, 'author mismatch')
          return
    if changed:
      write_forum(forum)
      self.send(json.dumps({'ok': True}), [('Content-Type','application/json')])
      return
    self.send_error(404, 'message not found')


  def post_forum_edit(self):
    params = self.params
    try:
      msg_id = int(params.get('id', [''])[0])
    except Exception:
      self.send_error(400, 'id required')
      return
    author = params.get('author', [''])[0].strip()
    content = params.get('content', [''])[0].strip()
    reply_idx = params.get('reply_idx', [None])[0]
    forum = read_forum()
    changed = False
    if reply_idx is not None:
      # Edition d'une réponse
      try:
        reply_idx = int(reply_idx)
      except Exception:
        self.send_error(400, 'reply_idx must be int')
        return
      for msg in forum:
        if msg.get('id') == msg_id:
          if 0 <= reply_idx < len(msg.get('replies', [])):
            if msg['replies'][reply_idx]['author'] == author:
              msg['replies'][reply_idx]['content'] = content
              changed = True
              break
            else:
              self.send_error(403, 'author mismatch')
              return
      if changed:
        write_forum(forum)
        self.send(json.dumps({'ok': True}), [('Content-Type','application/json')])
        return
      self.send_error(404, 'reply not found')
      return
    # Edition d'un message principal
    for msg in forum:
      if msg.get('id') == msg_id:
        if msg.get('author') == author:
          msg['content'] = content
          changed = True
          break
        else:
          self.send_error(403, 'author mismatch')
          return
    if changed:
      write_forum(forum)
      self.send(json.dumps({'ok': True}), [('Content-Type','application/json')])
      return
    self.send_error(404, 'message not found')


# Ouverture d'une connexion avec la base de données après vérification de sa présence
if not os.path.exists(BD_name):
    raise FileNotFoundError("BD {} non trouvée !".format(BD_name))
conn = sqlite3.connect(BD_name)

# Instanciation et lancement du serveur
httpd = socketserver.TCPServer(("", port_serveur), RequestHandler)
print("Serveur lancé sur port : ", port_serveur)
httpd.serve_forever()