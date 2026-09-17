import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../datos/modelos.dart';

/// Preferencia de tema del usuario: Sistema, Noche del Reino u Día del Reino.
///
/// El documento de experiencia fija el tema oscuro como predeterminado, pero
/// respetando la preferencia del sistema y permitiendo elegir en Ajustes.
///
/// El tema se guarda en dos sitios y eso es a propósito: en el disco del
/// teléfono, para que la app se pinte bien desde el primer fotograma sin
/// esperar a la red, y en el servidor, para que la elección viaje con la
/// cuenta. Lo que faltaba era la vuelta —ver `adoptarDelServidor`.
class ControladorTema extends ChangeNotifier {
  ControladorTema({ThemeMode inicial = ThemeMode.dark}) : _modo = inicial;

  static const String _clave = 'atenea_tema';

  ThemeMode _modo;

  /// ¿Este teléfono tiene una elección guardada, o está estrenando?
  bool _elegidoAqui = false;

  ThemeMode get modo => _modo;

  /// Traducción entre el tema del contrato y el de Flutter.
  ///
  /// Vive aquí, y no en la pantalla de Ajustes donde estaba, porque ahora la
  /// necesitan dos sitios y un mapeo duplicado es un mapeo que se desincroniza.
  static ThemeMode modoDe(PreferenciaTema tema) => switch (tema) {
        PreferenciaTema.sistema => ThemeMode.system,
        PreferenciaTema.oscuro => ThemeMode.dark,
        PreferenciaTema.claro => ThemeMode.light,
      };

  /// Etiqueta en español para la pantalla de ajustes.
  String get etiqueta => switch (_modo) {
        ThemeMode.system => 'Según el sistema',
        ThemeMode.dark => 'Noche del Reino',
        ThemeMode.light => 'Día del Reino',
      };

  Future<void> cargar() async {
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      final String? guardado = prefs.getString(_clave);
      if (guardado != null) {
        _modo = _desdeTexto(guardado);
        _elegidoAqui = true;
        notifyListeners();
      }
    } catch (_) {
      // Si las preferencias no están disponibles se mantiene el valor por
      // defecto; no es motivo para impedir el arranque de la aplicación.
    }
  }

  /// Aplica el tema que guarda la cuenta, si este teléfono no tenía ninguno.
  ///
  /// El caso que esto arregla se ve al reinstalar: el disco está vacío, así que
  /// la app arrancaba con el valor de fábrica —oscuro— mientras la pantalla de
  /// Ajustes marcaba el chip del servidor. El aprendiz veía «Día del Reino»
  /// seleccionado sobre una app pintada de noche.
  ///
  /// Gana lo local cuando existe, y no por capricho: es lo que esta persona
  /// eligió *en este teléfono*, y es lo único de los dos que puede haber
  /// cambiado sin que el servidor se enterase. El servidor solo rellena el
  /// hueco.
  Future<void> adoptarDelServidor(PreferenciaTema? tema) async {
    if (tema == null || _elegidoAqui) return;
    await cambiar(modoDe(tema));
  }

  Future<void> cambiar(ThemeMode nuevo) async {
    _elegidoAqui = true;
    if (nuevo == _modo) return;
    _modo = nuevo;
    notifyListeners();
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setString(_clave, _aTexto(nuevo));
    } catch (_) {
      // Preferencia no persistida: la sesión actual igualmente respeta la
      // elección del usuario.
    }
  }

  static String _aTexto(ThemeMode m) => switch (m) {
        ThemeMode.system => 'sistema',
        ThemeMode.dark => 'oscuro',
        ThemeMode.light => 'claro',
      };

  static ThemeMode _desdeTexto(String s) => switch (s) {
        'sistema' => ThemeMode.system,
        'claro' => ThemeMode.light,
        _ => ThemeMode.dark,
      };
}
