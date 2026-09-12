/// Estado del Inicio (P04): el panel del héroe.
///
/// Regla de la pantalla: ante un error de red **no se borra lo que ya se
/// mostraba**. Se conservan los datos en caché y se levanta [avisoEnCache]
/// para que el Inicio muestre el aviso discreto con "Reintentar".
library;

import 'package:flutter/foundation.dart';

import '../data/errores.dart';
import '../datos/repositorios.dart';

/// Carga y refresco del panel principal.
class ControladorPanel extends ChangeNotifier {
  ControladorPanel(this._repos);

  /// Pasado este tiempo el panel se considera viejo y se vuelve a pedir al
  /// entrar al Inicio. No es una duración de animación: es política de datos.
  static const Duration frescura = Duration(minutes: 2);

  final Repositorios _repos;

  Panel? _panel;
  bool _cargando = false;
  bool _refrescando = false;
  ErrorAtenea? _error;
  DateTime? _actualizadoEn;

  /// Panel vigente, o `null` mientras nunca se ha cargado.
  Panel? get panel => _panel;

  /// Primera carga en curso: la pantalla muestra esqueletos.
  bool get cargando => _cargando;

  /// Recarga silenciosa en curso (tirón para refrescar).
  bool get refrescando => _refrescando;

  /// Último error, ya en español.
  ErrorAtenea? get error => _error;

  /// Cuándo se obtuvieron estos datos.
  DateTime? get actualizadoEn => _actualizadoEn;

  /// ¿Hay algo que pintar aunque la última petición fallara?
  bool get hayDatos => _panel != null;

  /// Hubo error pero seguimos mostrando datos de antes.
  bool get avisoEnCache => _error != null && _panel != null;

  /// El panel está vacío y además falló: toca el estado de error completo.
  bool get errorSinDatos => _error != null && _panel == null;

  /// ¿Los datos ya envejecieron?
  bool get estaViejo {
    final DateTime? momento = _actualizadoEn;
    if (momento == null) return true;
    return DateTime.now().difference(momento) > frescura;
  }

  /// Atajos que el Inicio consulta a menudo.
  AccionContinuar get accionContinuar =>
      _panel?.accionContinuar ?? const AccionContinuar();

  /// Banner de generación en curso, si lo hay.
  BannerGeneracion? get bannerGeneracion => _panel?.bannerGeneracion;

  /// Saldo de oro que muestra la cabecera.
  int get saldoOro => _panel?.saldoOro ?? 0;

  /// Objetivo diario del día.
  ObjetivoDiario get objetivoDiario =>
      _panel?.objetivoDiario ?? const ObjetivoDiario();

  /// Racha vigente.
  Racha get racha => _panel?.racha ?? const Racha();

  /// Carga el panel. Si ya hay datos frescos no vuelve a pedirlo salvo que se
  /// pase [forzar].
  Future<void> cargar({bool forzar = false}) async {
    if (_cargando || _refrescando) return;
    if (!forzar && _panel != null && !estaViejo) return;
    if (_panel == null) {
      _cargando = true;
    } else {
      _refrescando = true;
    }
    notifyListeners();
    await _pedir();
  }

  /// Recarga explícita desde la pantalla (tirón o botón de reintento).
  Future<void> refrescar() async {
    if (_cargando || _refrescando) return;
    _refrescando = true;
    notifyListeners();
    await _pedir();
  }

  /// Olvida el panel al cerrar sesión.
  void limpiar() {
    _panel = null;
    _error = null;
    _actualizadoEn = null;
    _cargando = false;
    _refrescando = false;
    notifyListeners();
  }

  Future<void> _pedir() async {
    try {
      _panel = await _repos.panel.panel();
      _actualizadoEn = DateTime.now();
      _error = null;
    } catch (e) {
      _error = e is ErrorAtenea
          ? e
          : const ErrorAtenea(
              codigo: 'inesperado',
              mensaje: 'No pudimos actualizar tu Reino. Inténtalo de nuevo.',
            );
    } finally {
      _cargando = false;
      _refrescando = false;
      notifyListeners();
    }
  }
}
