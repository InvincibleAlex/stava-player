import random

class QueueManager:
    def __init__(self):
        self.queue = []            # Lista originală (ordinea din folder)
        self.shuffled_queue = []   # Lista amestecată (pentru Shuffle)
        self.history = []          # Istoric pentru butonul Back
        self.shuffle_history = []  # 🔥 Istoric separat PENTRU SHUFFLE, pentru a evita repetițiile
        self.max_history = 10      # Păstrăm doar ultimele 10 piese în istoric
        self.current_path = None
        
        # State
        self.is_shuffle = 0      # 0=Off, 1=On
        self.repeat_mode = 0     # 0=Off, 1=One, 2=All

    def update_history_for_new_song(self, current_file):
        if self.current_path and self.current_path != current_file:
            if not self.history or self.history[-1] != self.current_path:
                self.history.append(self.current_path)
                if len(self.history) > self.max_history:
                    self.history = self.history[-self.max_history:]

            if self.is_shuffle:
                self.shuffle_history.append(self.current_path)
                if len(self.shuffle_history) > 100:
                    self.shuffle_history = self.shuffle_history[-100:]

        self.current_path = current_file
        
        if self.is_shuffle and self.current_path in self.shuffled_queue:
            self.shuffled_queue.remove(self.current_path)

    def set_queue(self, files, current_file):
        """ Setează coada curentă și regenerează shuffle dacă e necesar """
        self.update_history_for_new_song(current_file)
        
        # Dacă lista e nouă, o actualizăm
        if files is not None and files != self.queue:
            self.queue = list(files)
            self.shuffled_queue = [] # Resetăm shuffle-ul vechi
            self.history = []        # Resetăm istoricul de Back
            self.shuffle_history = []# Resetăm și istoricul de Shuffle
            
            # Dacă Shuffle e activ și s-a schimbat folderul, generăm o coadă nouă
            if self.is_shuffle:
                self._regenerate_shuffle()
        
        # 🔥 FIX: Dacă lista e aceeași, NU regenerăm shuffle-ul (păstrăm ordinea).
        # Regenerăm doar dacă lista shuffle e goală (și nu e terminată natural)
        elif self.is_shuffle and not self.shuffled_queue:
             # Verificăm dacă e cazul să regenerăm (poate s-a terminat coada)
             # Dar aici e safe să regenerăm dacă e goală.
             pass 

    def _regenerate_shuffle(self):
        """ Generează o nouă ordine aleatorie, excluzând piesa curentă din start """
        if not self.queue: return
        
        self.shuffled_queue = list(self.queue)
        random.shuffle(self.shuffled_queue)
        
        # Scoatem piesa curentă din lista de "urmează" (pentru că o ascultăm acum)
        if self.current_path in self.shuffled_queue:
            self.shuffled_queue.remove(self.current_path)

        # 🔥 NOU: Ne asigurăm că următoarea piesă nu e una din cele ascultate recent
        if self.shuffled_queue and self.shuffle_history:
            # Câte piese recente să evităm? Un sfert din listă, până la maxim 50 de piese.
            avoid_count = min(50, len(self.queue) // 4)
            recent_songs = self.shuffle_history[-avoid_count:]
            
            # Dacă prima piesă din noua listă e una recentă, o mutăm la final.
            # Facem asta de câteva ori pentru a crește șansele unei piese "fresh".
            moved_count = 0
            # Limită pentru a nu intra în buclă infinită pe playlist-uri mici
            max_moves = len(self.shuffled_queue) - 1
            while self.shuffled_queue and self.shuffled_queue[0] in recent_songs and moved_count < max_moves:
                song_to_move = self.shuffled_queue.pop(0)
                self.shuffled_queue.append(song_to_move)
                moved_count += 1

    def get_next_song(self):
        """ Returnează calea următoarei piese sau None """
        if not self.queue: return None

        # 1. Shuffle Mode
        if self.is_shuffle:
            if not self.shuffled_queue:
                # Dacă s-a terminat coada shuffle
                if self.repeat_mode == 0: 
                    return None # Stop playback
                
                # Dacă Repeat All e activ, regenerăm
                self._regenerate_shuffle()
                # Edge case: Dacă e o singură piesă în listă
                if not self.shuffled_queue and self.queue:
                     return self.queue[0]

            if self.shuffled_queue:
                return self.shuffled_queue.pop(0)
        
        # 2. Normal Mode
        else:
            try:
                idx = self.queue.index(self.current_path)
                if idx + 1 >= len(self.queue):
                    # Ultima piesă
                    if self.repeat_mode == 0: return None
                    return self.queue[0] # Loop la început
                return self.queue[idx + 1]
            except ValueError:
                return self.queue[0]
        
    def peek_next_song(self):
        """ Returnează calea următoarei piese FĂRĂ a modifica coada (pentru Preload) """
        if not self.queue: return None

        if self.is_shuffle:
            if self.shuffled_queue:
                return self.shuffled_queue[0]
            # Dacă coada shuffle e goală, nu putem ghici ce urmează (random), deci nu preloadăm
            return None
        
        # 2. Normal Mode
        else:
            try:
                idx = self.queue.index(self.current_path)
                if idx + 1 >= len(self.queue):
                    # Ultima piesă
                    if self.repeat_mode == 0: return None
                    return self.queue[0] # Loop la început
                return self.queue[idx + 1]
            except ValueError:
                return self.queue[0]
        
        return None

    def get_prev_song(self):
        """ Returnează calea piesei anterioare """
        # Folosim strict istoricul; dacă s-a terminat, nu mai mergem înapoi.
        if self.history:
            return self.history.pop()

        return None

    def peek_prev_song(self):
        """ Returnează calea piesei anterioare FĂRĂ a modifica istoricul """
        if self.history:
            return self.history[-1]

        return None