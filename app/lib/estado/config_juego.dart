/// La configuración pública del Reino (`GET /config/public`).
///
/// Es el único sitio de la aplicación donde se recoge configuración de juego, y
/// por eso vive aquí y no dentro de una pantalla. Estuvo mucho tiempo declarado
/// dentro de `pantallas/perfil/racha.dart`, sirviendo únicamente para pintar
/// las opciones del objetivo diario; cuando el recordatorio local necesitó las
/// horas del Reino, la alternativa habría sido una segunda caché —o, peor, las
/// horas escritas a mano en Dart, que es exactamente lo que §8.10 prohíbe.
///
/// Se pide con `sinAuth: true`, así que puede llegar antes de que haya sesión.
library;

import 'package:flutter/foundation.dart';

import '../data/errores.dart';
import '../datos/repositorios.dart';
import '../nucleo/plan_recordatorio.dart';

/// Configuración pública del juego: opciones de objetivo y horas de aviso.
class ControladorConfigJuego extends ChangeNotifier {
  ControladorConfigJuego(this._repos);

  final Repositorios _repos;

  ConfigPublica? _config;
  bool _cargando = false;

  /// Configuración vigente, o `null` si todavía no llegó.
  ConfigPublica? get config => _config;

  /// ¿Se está pidiendo?
  bool get cargando => _cargando;

  /// Trae la configuración una sola vez.
  Future<void> cargar() async {
    if (_cargando || _config != null) return;
    _cargando = true;
    notifyListeners();
    try {
      _config = await _repos.gamificacion.configPublica();
    } on ErrorAtenea {
      // Sin configuración se usan las opciones documentadas del contrato:
      // no es motivo para dejar al usuario sin poder cambiar su objetivo.
    } finally {
      _cargando = false;
      notifyListeners();
    }
  }

  /// Opciones de meta para un tipo de objetivo (`goal.*.options` de §5.6).
  List<int> opcionesDe(TipoObjetivo tipo) {
    final String clave = switch (tipo) {
      TipoObjetivo.minutos => 'goal.minutes.options',
      TipoObjetivo.actividades => 'goal.activities.options',
      TipoObjetivo.xp => 'goal.xp.options',
    };
    final List<int> delReino = <int>[
      for (final String v in _config?.lista(clave) ?? const <String>[])
        if (int.tryParse(v) != null) int.parse(v),
    ];
    if (delReino.isNotEmpty) return delReino;
    return _opcionesDocumentadas[tipo] ?? const <int>[];
  }

  /// Valores iniciales que documenta el contrato (§5.6) y que solo se usan
  /// mientras la configuración del servidor no está disponible.
  static const Map<TipoObjetivo, List<int>> _opcionesDocumentadas =
      <TipoObjetivo, List<int>>{
    TipoObjetivo.minutos: <int>[10, 20, 30, 45],
    TipoObjetivo.actividades: <int>[1, 3, 5, 8],
    TipoObjetivo.xp: <int>[50, 100, 200, 350],
  };

  // ---------------------------------------------------------------------------
  // Las horas del Reino, para el recordatorio local y para Ajustes
  // ---------------------------------------------------------------------------

  /// Hora del recordatorio cuando el aprendiz no fija una.
  HoraLocal? get horaPorDefecto =>
      _hora('notifications.reminder.default_hour');

  /// Hora del segundo aviso de la noche.
  HoraLocal? get horaUltimaLlamada => _hora('notifications.last_call.hour');

  /// Principio de la franja en la que el Reino puede avisar.
  HoraLocal? get ventanaDesde => _borde('notifications.reminder.window', 'start');

  /// Final de esa franja. Lo que se elija por encima, el servidor lo acota.
  HoraLocal? get ventanaHasta => _borde('notifications.reminder.window', 'end');

  /// Principio de las horas de silencio de fábrica.
  HoraLocal? get silencioDesde => _borde('notifications.quiet_hours', 'start');

  /// Final de las horas de silencio de fábrica.
  HoraLocal? get silencioHasta => _borde('notifications.quiet_hours', 'end');

  /// Devuelve `null` mientras la configuración no haya llegado.
  ///
  /// Que devuelva `null` y no un valor de respaldo es deliberado: quien
  /// pregunta —la cadena de recordatorios— prefiere no programar nada antes que
  /// programar a una hora inventada. Un aviso a las 19:00 para quien nunca pidió
  /// las 19:00 es peor que ningún aviso.
  HoraLocal? _hora(String clave) {
    final String texto = _config?.texto(clave) ?? '';
    return texto.isEmpty ? null : HoraLocal.desdeTexto(texto);
  }

  HoraLocal? _borde(String clave, String extremo) {
    final Map<String, dynamic> franja = _config?.mapa(clave) ?? <String, dynamic>{};
    return HoraLocal.desdeTexto(franja[extremo]);
  }

  /// Rellena el espejo del recordatorio con lo que manda el Reino.
  ///
  /// Sin tocar lo que eligió el aprendiz ni lo que sabe el teléfono: son las
  /// tres clases de dato del espejo y cada una tiene su dueño.
  EspejoRecordatorio anotarEn(EspejoRecordatorio espejo) => espejo.copiarCon(
        horaPorDefecto: horaPorDefecto,
        horaUltimaLlamada: horaUltimaLlamada,
        ventanaDesde: ventanaDesde,
        ventanaHasta: ventanaHasta,
      );
}
