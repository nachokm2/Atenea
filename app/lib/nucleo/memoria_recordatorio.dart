/// Dónde vive el espejo del recordatorio entre una sesión y la siguiente.
///
/// El espejo no puede depender de la red: cuando la aplicación se va a segundo
/// plano —que es el único momento en que se escriben alarmas— puede no haber
/// conexión, y desde luego no hay tiempo para una petición. Así que lo último
/// que se supo se guarda en el disco del teléfono y se lee al arrancar.
///
/// **Una clave por campo, y no un JSON entero.** Un blob serializado se rompe
/// entero el día que un campo aparece o desaparece; las claves sueltas
/// sobreviven, porque lo que falta se lee como ausente y el planificador ya
/// sabe qué hacer con eso: no programar lo que dependa de ello.
///
/// Lo que aquí se guarda es de este aparato y de nadie más. El permiso del
/// sistema operativo, en particular, **nunca** viaja al servidor: negar los
/// avisos en el móvil viejo no puede apagar los del nuevo.
library;

import 'package:shared_preferences/shared_preferences.dart';

import '../datos/dtos.dart';
import 'plan_recordatorio.dart';

/// Prefijo común, para poder borrarlo todo de una pasada al cerrar sesión.
const String _prefijo = 'atenea_recordatorio_';

const String _kIntencion = '${_prefijo}intencion';
const String _kPermiso = '${_prefijo}permiso';
const String _kModo = '${_prefijo}modo';
const String _kHoraManual = '${_prefijo}hora_manual';
const String _kUltimaLlamada = '${_prefijo}ultima_llamada';
const String _kSilencioDesde = '${_prefijo}silencio_desde';
const String _kSilencioHasta = '${_prefijo}silencio_hasta';
const String _kHoraPorDefecto = '${_prefijo}hora_por_defecto';
const String _kHoraUltimaLlamada = '${_prefijo}hora_ultima_llamada';
const String _kVentanaDesde = '${_prefijo}ventana_desde';
const String _kVentanaHasta = '${_prefijo}ventana_hasta';
const String _kUltimaPractica = '${_prefijo}ultima_practica';

/// Todas las claves del espejo. Cerrada, para poder olvidarlo entero.
const List<String> _claves = <String>[
  _kIntencion,
  _kPermiso,
  _kModo,
  _kHoraManual,
  _kUltimaLlamada,
  _kSilencioDesde,
  _kSilencioHasta,
  _kHoraPorDefecto,
  _kHoraUltimaLlamada,
  _kVentanaDesde,
  _kVentanaHasta,
  _kUltimaPractica,
];

/// Lee y escribe el espejo en el disco del teléfono.
class MemoriaRecordatorio {
  /// Lo último que este teléfono supo.
  ///
  /// Nunca lanza: si las preferencias no están disponibles devuelve un espejo
  /// vacío, y un espejo vacío no programa nada. Fallar aquí no puede impedir
  /// que Atenea arranque.
  Future<EspejoRecordatorio> leer() async {
    try {
      final SharedPreferences disco = await SharedPreferences.getInstance();
      return EspejoRecordatorio(
        intencionAvisos: disco.getBool(_kIntencion) ?? false,
        permisoConcedido: disco.getBool(_kPermiso) ?? false,
        modo: ModoRecordatorio.desdeApi(disco.getString(_kModo)),
        horaManual: HoraLocal.desdeTexto(disco.getString(_kHoraManual)),
        ultimaLlamada: disco.getBool(_kUltimaLlamada) ?? false,
        silencioDesde: HoraLocal.desdeTexto(disco.getString(_kSilencioDesde)),
        silencioHasta: HoraLocal.desdeTexto(disco.getString(_kSilencioHasta)),
        horaPorDefecto: HoraLocal.desdeTexto(disco.getString(_kHoraPorDefecto)),
        horaUltimaLlamada:
            HoraLocal.desdeTexto(disco.getString(_kHoraUltimaLlamada)),
        ventanaDesde: HoraLocal.desdeTexto(disco.getString(_kVentanaDesde)),
        ventanaHasta: HoraLocal.desdeTexto(disco.getString(_kVentanaHasta)),
        ultimaPracticaLocal: DateTime.tryParse(
          disco.getString(_kUltimaPractica) ?? '',
        ),
      );
    } catch (_) {
      return const EspejoRecordatorio();
    }
  }

  /// Guarda el espejo. Un campo nulo se borra en vez de dejar el anterior.
  ///
  /// Borrar importa: si el aprendiz pasa de hora fija a modo inteligente, dejar
  /// la hora vieja en el disco haría que el teléfono siguiera avisando a una
  /// hora que ya nadie pidió.
  Future<void> guardar(EspejoRecordatorio espejo) async {
    try {
      final SharedPreferences disco = await SharedPreferences.getInstance();
      await disco.setBool(_kIntencion, espejo.intencionAvisos);
      await disco.setBool(_kPermiso, espejo.permisoConcedido);
      await disco.setString(_kModo, espejo.modo.api);
      await disco.setBool(_kUltimaLlamada, espejo.ultimaLlamada);
      await _hora(disco, _kHoraManual, espejo.horaManual);
      await _hora(disco, _kSilencioDesde, espejo.silencioDesde);
      await _hora(disco, _kSilencioHasta, espejo.silencioHasta);
      await _hora(disco, _kHoraPorDefecto, espejo.horaPorDefecto);
      await _hora(disco, _kHoraUltimaLlamada, espejo.horaUltimaLlamada);
      await _hora(disco, _kVentanaDesde, espejo.ventanaDesde);
      await _hora(disco, _kVentanaHasta, espejo.ventanaHasta);

      final DateTime? practica = espejo.ultimaPracticaLocal;
      if (practica == null) {
        await disco.remove(_kUltimaPractica);
      } else {
        await disco.setString(
          _kUltimaPractica,
          DateTime(practica.year, practica.month, practica.day)
              .toIso8601String(),
        );
      }
    } catch (_) {
      // Sin disco el recordatorio se pierde al cerrar la aplicación. Es una
      // degradación, no un fallo: nada de lo que hace Atenea depende de esto.
    }
  }

  /// Borra el espejo entero.
  ///
  /// Se llama al cerrar sesión, y no es una limpieza cosmética. Sin esto, un
  /// teléfono compartido le diría a la siguiente persona «en este teléfono
  /// todavía no hay práctica de hoy» sobre la práctica de otra, y una cuenta
  /// nueva heredaría las horas de la anterior.
  Future<void> olvidar() async {
    try {
      final SharedPreferences disco = await SharedPreferences.getInstance();
      for (final String clave in _claves) {
        await disco.remove(clave);
      }
    } catch (_) {
      // Ver `guardar`.
    }
  }

  Future<void> _hora(
    SharedPreferences disco,
    String clave,
    HoraLocal? hora,
  ) async {
    if (hora == null) {
      await disco.remove(clave);
    } else {
      await disco.setString(clave, hora.texto);
    }
  }
}
