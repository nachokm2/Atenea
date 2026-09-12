/// Sobre de paginación por cursor de la API de Atenea (§8.2 del contrato).
///
/// La API responde `{"items": [...], "page": {"limit", "next_cursor",
/// "has_more", "total"}}`. `total` puede venir nulo en listas grandes y
/// `next_cursor` es un cursor opaco en base64 que jamás se interpreta en el
/// cliente: se devuelve tal cual en la siguiente petición.
library;

/// Metadatos de una página: tamaño, cursor siguiente y si quedan más filas.
class InfoPagina {
  const InfoPagina({
    this.limite = 20,
    this.cursorSiguiente,
    this.hayMas = false,
    this.total,
  });

  /// Lee el sobre `page`. Tolera que falte por completo.
  factory InfoPagina.desdeJson(Map<String, dynamic>? json) {
    if (json == null) return const InfoPagina();
    final String? cursor = _texto(json['next_cursor'] ?? json['cursor']);
    return InfoPagina(
      limite: _entero(json['limit'], 20),
      cursorSiguiente: (cursor == null || cursor.isEmpty) ? null : cursor,
      hayMas: _booleano(json['has_more'], false),
      total: json['total'] == null ? null : _entero(json['total'], 0),
    );
  }

  /// Tamaño de página pedido (por defecto 20, máximo 100).
  final int limite;

  /// Cursor opaco de la siguiente página; nulo cuando no quedan más.
  final String? cursorSiguiente;

  /// ¿Hay más resultados después de esta página?
  final bool hayMas;

  /// Total de filas, solo cuando el servidor lo calcula barato.
  final int? total;

  /// ¿Se puede pedir otra página?
  bool get puedeSeguir => hayMas && cursorSiguiente != null;
}

/// Página tipada de resultados: los elementos ya convertidos más sus metadatos.
class Pagina<T> {
  const Pagina({required this.elementos, required this.info});

  /// Página vacía, útil como estado inicial de un controlador.
  Pagina.vacia()
      : elementos = <T>[],
        info = const InfoPagina();

  /// Convierte `{"items": [...], "page": {...}}` usando [desde] por elemento.
  ///
  /// Tolera respuestas que devuelvan la lista desnuda, o que usen `data`,
  /// `datos` o `results` como nombre de la colección.
  factory Pagina.desdeJson(
    Object? json,
    T Function(Map<String, dynamic> json) desde,
  ) {
    if (json is List) {
      return Pagina<T>(
        elementos: _convertir<T>(json, desde),
        info: const InfoPagina(),
      );
    }
    if (json is! Map) return Pagina<T>.vacia();
    final Map<String, dynamic> mapa = Map<String, dynamic>.from(json);
    final Object? crudos = mapa['items'] ??
        mapa['data'] ??
        mapa['datos'] ??
        mapa['results'] ??
        mapa['elementos'];
    final Map<String, dynamic>? sobre =
        mapa['page'] is Map ? Map<String, dynamic>.from(mapa['page'] as Map) : null;
    return Pagina<T>(
      elementos: _convertir<T>(crudos, desde),
      info: InfoPagina.desdeJson(sobre),
    );
  }

  /// Elementos de esta página, en el orden que envió el servidor.
  final List<T> elementos;

  /// Metadatos de paginación.
  final InfoPagina info;

  /// ¿La página no trajo nada?
  bool get estaVacia => elementos.isEmpty;

  /// Cursor para pedir la página siguiente, o nulo si esta es la última.
  String? get cursorSiguiente => info.cursorSiguiente;

  /// Devuelve una nueva página con los elementos de [otra] añadidos al final,
  /// conservando los metadatos de [otra] (scroll infinito).
  Pagina<T> mas(Pagina<T> otra) => Pagina<T>(
        elementos: <T>[...elementos, ...otra.elementos],
        info: otra.info,
      );

  /// Transforma los elementos conservando los metadatos.
  Pagina<R> mapear<R>(R Function(T elemento) f) => Pagina<R>(
        elementos: elementos.map(f).toList(growable: false),
        info: info,
      );

  static List<T> _convertir<T>(
    Object? crudos,
    T Function(Map<String, dynamic> json) desde,
  ) {
    if (crudos is! List) return <T>[];
    final List<T> salida = <T>[];
    for (final Object? bruto in crudos) {
      if (bruto is Map) salida.add(desde(Map<String, dynamic>.from(bruto)));
    }
    return salida;
  }
}

int _entero(Object? valor, int porDefecto) {
  if (valor is int) return valor;
  if (valor is num) return valor.round();
  if (valor is String) return int.tryParse(valor.trim()) ?? porDefecto;
  return porDefecto;
}

bool _booleano(Object? valor, bool porDefecto) {
  if (valor is bool) return valor;
  if (valor is num) return valor != 0;
  if (valor is String) {
    final String v = valor.trim().toLowerCase();
    if (v == 'true' || v == '1' || v == 'si' || v == 'sí') return true;
    if (v == 'false' || v == '0' || v == 'no') return false;
  }
  return porDefecto;
}

String? _texto(Object? valor) => valor?.toString();
