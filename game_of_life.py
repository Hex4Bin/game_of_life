"""
https://en.wikipedia.org/wiki/Conway%27s_Game_of_Life
Az alap ötlet, hogy minden sejt egy objektum, aminek referenciája van a szomszédjaira.
Bár a sejtek bejárása nem e referenciák mentén történik, de ilyen szempontból egy nagy
láncolt lista az egész program.
A sejteket Cell-nek nevezem, és az a terület, ahol a sejtek léteznek az univerzum (Universe).
Az alapműködés szerint a config_file.config tartalma kirajzolódik egy tkinter-es canvas-ra,
és 200ms-os tick mellett elindul a szimuláció.
"""

import pathlib
import re
import tkinter as tk
from typing import Optional, Type, TypedDict

# Rendereléshez
TICK = 200  # Univerzum órája ms-ban
CELL_SIZE_PX = 24  # Grid mérete renderelésnél

# Tkinter-es color code-ok
CELL_DEAD_COLOR = 'white'
CELL_ALIVE_COLOR = 'black'


# Az univerzum szélénél ne kelljen None-okat csekkolni.
class NullCell:
    _state = 0


class Cell:
    """
    Ez reprezentálja egy sejt állapotát. A pozícióját is hordozza az univerzumban,
    igaz, ez csak a kirajzoláshoz és a debuggoláshoz kell.
    """

    # Az univerzum szélét singleton-nak tekintjük, ezért az class var
    NULL = NullCell()

    def __init__(self, is_alive: bool, pos_x: int, pos_y: int):
        self._state = int(is_alive)

        # A sejt állapotváltozása nem végleges addig, amíg a self.commit() meghívásra nem kerül.
        # Így a sejtek új állapotának megállapításához anélkül használhatjuk fel a régi éréket, hogy
        # közben új univerzumot kéne építeni.
        self._state_dirty = None
        self.pos_x = pos_x
        self.pos_y = pos_y

        # Nem szeretném a környező sejteket index alapján kikeresni. Ez az objektum
        # referenciákat tárol majd el a szomszédos sejtekre, és csinos apival lehet hivatkozni rájuk
        self.neighbours = Neighbours()

        # tkinter-es rectangle referenciája, a canvas update-hez kell majd
        self.rectangle = None

    @property
    def is_alive(self):
        return bool(self._state)

    @is_alive.setter
    def is_alive(self, alive: bool):
        """
        Ezzel a propertyvel szétválik a sejt aktuális- és végállapota
        """

        assert self._state_dirty is None
        self._state_dirty = int(alive)

    def commit(self):
        """
        Ez a metódus véglegesíti a sejt állapotát
        """

        self._state = self._state_dirty
        self._state_dirty = None

    def __repr__(self):
        """
        Csak a debuggolás végett
        """

        return f'<Cell({self.pos_x}, {self.pos_y})>'


class Neighbour:
    """
    Ez egy descriptor osztály.
    Ha osztályváltozóként viselkedik, akkor relatív indexeket ad vissza, amivel
    megállapítható lesz a sejt szomszédsága. Ilyen szempontból ezek a descriptorok
    konstansokként/enumként viselkednek.
    Ezeket az indexeket majd az Universe konstruktora hasznosítja.
    Ha példványváltozóként használod, akkor visszatér a szomszédos cellával, vagy a NullCell
    referenciájával, ha az univerzum szélén vagyunk.
    Technikailag lehet fekete lyuk is az univerzumban.
    """

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self._name: Optional[str] = None

    def __set_name__(self, owner: Type['Neighbours'], name: str):
        self._name = name

    def __get__(self, instance: Optional['Neighbours'], owner: Type['Neighbours']):
        if instance is None:
            return self

        else:
            return instance.__dict__.get(self._name, Cell.NULL)

    def __set__(self, instance: Optional['Neighbours'], value):
        if value is not None:
            instance.__dict__[self._name] = value


class Neighbours:
    """
    Ezek a descriptorok kódolják, hogy egy tetszőleges sejt szomszédjainak
    mik a relatív koordinátái.
    A koordináták az "O"-hoz képest relatívak, e szerint:
       Y
       ^
       |
       +---+---+---+
    -1 |   |   |   |
       +---+---+---+
     0 |   | O |   |
       +---+---+---+
     1 |   |   |   |
       +---+---+---+  ---> X
        -1   0   1
    """

    top = Neighbour(0, -1)
    top_right = Neighbour(1, -1)
    right = Neighbour(1,  0)
    bottom_right = Neighbour(1,  1)
    bottom = Neighbour(0,  1)
    bottom_left = Neighbour(-1,  1)
    left = Neighbour(-1,  0)
    top_left = Neighbour(-1, -1)

    def get_alive_count(self) -> int:
        return self.top._state \
            + self.top_right._state \
            + self.right._state \
            + self.bottom_right._state \
            + self.bottom._state \
            + self.bottom_left._state \
            + self.left._state \
            + self.top_left._state


class Universe:
    """
    Ez reprezentálja a sejtek (véges) univerzumát
    """

    def __init__(self, width: int, height: int):
        # Két kollekcióba gyűjtjük a sejtek referenciáját: az egyik az X-Y koordináta szerinti
        # eléréshez gyors (ez a self._board), a másik az iteráláshoz (ez egy sima 1D-s tömb, a self._cells)
        self._board: list[list[Cell]] = []
        board = self._board
        self._cells: list[Cell] = []

        # Kevésbé stresszes felépíteni az univerzumot, ha két menetben tesszük azt:
        # 1. Létrehozzuk az összes cell-t. Így nem kell számolgatnunk, meg előre-hátra
        # nézelődnünk a tömbben appendolás közben, ellenőrizve, hogy melyik szomszéd
        # jött épp létre.
        for row_ptr in range(height):
            row = []
            board.append(row)

            for col_ptr in range(width):
                cell = Cell(False, col_ptr, row_ptr)
                row.append(cell)
                self._cells.append(cell)

        def get_neighbour(neighbour: Neighbour) -> Optional[Cell]:
            # Itt a classvart hasznosítjuk, aminek van x és y koordinátája.
            # A nested functionben elérjük a külső ciklusváltozókat is

            x = col_ptr + neighbour.x
            y = row_ptr + neighbour.y

            if -1 < x < width and -1 < y < height:
                return board[y][x]

        # 2. Bejárjuk az összes cell-t, és beállítjuk, hogy kinek-merre-milyen szomszédja van.
        for row_ptr, row in enumerate(board):
            for col_ptr, cell in enumerate(row):
                # Ezért érte meg ezeket a Neighbour descriptorokat megírni.
                cell.neighbours.top = get_neighbour(Neighbours.top)
                cell.neighbours.top_right = get_neighbour(Neighbours.top_right)
                cell.neighbours.right = get_neighbour(Neighbours.right)
                cell.neighbours.bottom_right = get_neighbour(
                    Neighbours.bottom_right)
                cell.neighbours.bottom = get_neighbour(Neighbours.bottom)
                cell.neighbours.bottom_left = get_neighbour(
                    Neighbours.bottom_left)
                cell.neighbours.left = get_neighbour(Neighbours.left)
                cell.neighbours.top_left = get_neighbour(Neighbours.top_left)

    def __setitem__(self, key: tuple[int, int], is_alive: bool):
        # Az X, Y szerinti koordinátákat kételemű slice-olással lehet írni
        x, y = key
        cell = self._board[y][x]
        cell.is_alive = is_alive
        cell.commit()

    @property
    def cells(self):
        return self._cells

    def tick(self):
        """
        Lefuttat egy iterációt az univerzumban
        """

        # Sokat gyorsít majd a kirajzolásnál, ha csak azokat a sejteket rajzoljuk újra,
        # amelyek állapota megváltozott.
        changed = []

        for cell in self._cells:
            # Lásd: game of life szabályrendszere
            alive_neighbour_count = cell.neighbours.get_alive_count()
            if cell.is_alive:
                if not (alive_neighbour_count == 2 or alive_neighbour_count == 3):
                    cell.is_alive = False
                else:
                    cell.is_alive = True
                changed.append(cell)

            else:
                if alive_neighbour_count == 3:
                    cell.is_alive = True
                    changed.append(cell)

        # Minden levegőben lógó állapot véglegesítése
        for cell in changed:
            cell.commit()

        return changed

    def to_list(self) -> list[list[bool]]:
        """
        Tömbök tömbjét adja vissza. A belső tömbök a tábla sorait reprezentálják.
        A tömbök elemei bool-ok, ami ha True, akkor a sejt életben van. Ha halott, akkor False.
        Ezt a metódust csak a feladatmegoldás hasznosítja. A belső működéshez és a rendereléshez
        nincs rá szükség.
        """
        retval = []

        for row in self._board:
            retval_row = []
            retval.append(retval_row)
            for cell in row:
                retval_row.append(cell.is_alive)

        return retval


class Config(TypedDict):
    """
    Ez hordozza a config fájlból beolvasott adatokat
    """
    halott_sejt: str
    elo_sejt: str
    tabla: list[list[str]]


def read_config_file(filename: str) -> Config:
    """
    Parse-olja a kapott filename útvonalon található fájlt.
    """

    table_lines = []
    not_alive_char = None
    alive_char = None

    # Hasonlóan az Universe felépítéséhez, ez a metódus is két menetben olvassa be a fájlt.
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('tabla:'):
                # Táblázat kontextusában vagyunk.
                assert next(f).strip() == '"'
                #  Elkezdjük pörgetni a fájl sorait
                for table_line in f:
                    table_line = table_line.strip()
                    if table_line == '"':
                        break
                    else:
                        table_lines.append(table_line)

            # Idézőjelek közti egyetlen egy karaktert várunk el.
            elif match := re.match(r'^halott_sejt:\s*"(.)"$', line):
                not_alive_char = match[1].strip()

            elif match := re.match(r'^elo_sejt:\s*"(.)"$', line):
                alive_char = match[1].strip()

    # Jönnek az ellenőrzések
    if not alive_char:
        raise AttributeError

    if not not_alive_char:
        raise AttributeError

    table = []
    table_line_lengths = set()
    for table_line in table_lines:
        line_chars = list(table_line)
        # Nem maradhat semmilyen karakter se, ha kivonjuk a táblázat sorának karaktereiből képzett halmazból a
        # halott- és élő karakterek halmazát.
        if set(line_chars) - {alive_char, not_alive_char} != set():
            raise ValueError

        table_line_lengths.add(len(line_chars))
        # A sorhosszok se bóklászhatnak össze-vissza
        if not len(set(table_line_lengths)) == 1:
            raise ValueError

        table.append(line_chars)

    return Config(
        halott_sejt=not_alive_char,
        elo_sejt=alive_char,
        tabla=table
    )


def next_state(config: Config):
    """
    Inicializálja a Config alapján az univerzumot, és visszatér annak az
    állapotával egyetlen iteráció után.
    """
    width = len(config['tabla'][0])
    height = len(config['tabla'])

    # Bemásoljuk a configból a táblát az univerzumba
    universe = Universe(width, height)
    for row_ptr, row in enumerate(config['tabla']):
        for col_ptr, cell in enumerate(row):
            if cell == config['elo_sejt']:
                universe[col_ptr, row_ptr] = True

    universe.tick()

    table = universe.to_list()
    for row_ptr, row in enumerate(table):
        for col_ptr, is_alive in enumerate(row):
            if is_alive:
                char = config['elo_sejt']
            else:
                char = config['halott_sejt']

            table[row_ptr][col_ptr] = char

    return Config(
        elo_sejt=config['elo_sejt'],
        halott_sejt=config['halott_sejt'],
        tabla=table
    )


if __name__ == '__main__':
    # A config_file.config mindig a main.py mellett kell hogy létezzen.
    config = read_config_file(
        str(pathlib.Path(__file__).parent / 'config_file.config'))

    # Animáció -----------------------------------------------------------------
    # Ezt szabadon kijelenthetjük, hisz a config betöltése gondoskodik róla,
    # hogy minden sor egyforma hosszú legyen
    width = len(config['tabla'][0])
    height = len(config['tabla'])

    # Átmásoljuk a config-ból a sejteket az univerzumba
    universe = Universe(width, height)
    for row_ptr, row in enumerate(config['tabla']):
        for col_ptr, cell in enumerate(row):
            if cell == config['elo_sejt']:
                universe[col_ptr, row_ptr] = True

    root = tk.Tk()
    root.title("Game of Life")
    root.geometry(f'{width * CELL_SIZE_PX}x{height * CELL_SIZE_PX}')

    canvas = tk.Canvas(root, width=width * CELL_SIZE_PX,
                       height=height * CELL_SIZE_PX)
    canvas.pack()

    def render(tick: bool = True):
        """
        Alapállapot renderelése, ha tick = False, egyébként pedig
        az új állapot során változott Cell-ek renderelése.
        """

        if tick:
            cells = universe.tick()
        else:
            cells = universe.cells

        for cell in cells:
            fill = CELL_DEAD_COLOR if not cell.is_alive else CELL_ALIVE_COLOR

            if (rect := cell.rectangle) is None:
                # Pótoljuk a hiányzó rectangle-öket
                cell.rectangle = rect = canvas.create_rectangle(
                    cell.pos_x * CELL_SIZE_PX, cell.pos_y * CELL_SIZE_PX,
                    (cell.pos_x + 1) * CELL_SIZE_PX, (cell.pos_y + 1) * CELL_SIZE_PX,
                )

            # Rectangle-ök átszínezése
            canvas.itemconfig(rect, fill=fill)

        # Render loop
        root.after(TICK, render)

    # Első render, simán csak az univerzum állapotával
    render(tick=False)
    root.mainloop()
