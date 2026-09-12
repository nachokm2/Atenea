import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Preferencia de tema del usuario: Sistema, Noche del Reino u Día del Reino.
///
/// El documento de experiencia fija el tema oscuro como predeterminado, pero
/// respetando la preferencia del sistema y permitiendo elegir en Ajustes.
class ControladorTema extends ChangeNotifier {
  ControladorTema({ThemeMode inicial = ThemeMode.dark}) : _modo = inicial;

  static const String _clave = 'atenea_tema';

  ThemeMode _modo;

  ThemeMode get modo => _modo;

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
        notifyListeners();
      }
    } catch (_) {
      // Si las preferencias no están disponibles se mantiene el valor por
      // defecto; no es motivo para impedir el arranque de la aplicación.
    }
  }

  Future<void> cambiar(ThemeMode nuevo) async {
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
