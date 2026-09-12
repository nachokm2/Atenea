/// Cola de celebraciones (§5.3 del documento de UX y §7.10 del contrato).
///
/// Recibe un [ReciboRecompensas] y lo convierte en una secuencia ordenada:
///
/// 1. Los pasos que el servidor marca como overlay (racha, subida de nivel e
///    ítem) se muestran **uno a uno**, como máximo tres, en el orden que fija
///    `presentation_order`. El contrato es autoritativo: aquí no se reordena
///    ni se infiere nada.
/// 2. El resto (XP, oro, dominio, logros y misiones) se entrega como chips
///    para la pantalla de resumen (P10/P12).
///
/// Garantías de la cola:
///
/// - Ninguna celebración bloquea más de [limiteBloqueo] (2,4 s, por debajo de
///   los 2,5 s que fija §3.3 regla 3): pasado ese tiempo [listaParaContinuar]
///   es `true`.
/// - [descartar] funciona desde el primer fotograma: un toque siempre salta.
/// - Con movimiento reducido no hay espera: la celebración nace lista y su
///   [Celebracion.duracion] es cero, para que la pantalla pinte la versión
///   estática.
/// - Nunca hay dos celebraciones a la vez: se encadenan.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../design/tokens.dart';
import '../datos/repositorios.dart';

// Las pantallas que pintan celebraciones necesitan estos tipos; se reexportan
// para que no tengan que importar toda la capa de datos.
export '../datos/repositorios.dart'
    show
        ConocimientoRecibo,
        DeltaDominio,
        HitoRacha,
        ItemRecibo,
        LogroRecibo,
        MisionRecibo,
        NivelRecibo,
        OroRecibo,
        PasoCelebracion,
        RachaRecibo,
        ReciboRecompensas,
        RecompensaSimple,
        XpRecibo;

/// Cómo se presenta una celebración.
enum FormatoCelebracion {
  /// Overlay a pantalla completa (P13, P14 y el de racha).
  overlay,

  /// Chip dentro de la pantalla de resumen.
  chip,
}

/// Una celebración concreta, ya con su texto en español.
class Celebracion {
  const Celebracion({
    required this.paso,
    required this.formato,
    required this.recibo,
    required this.titulo,
    required this.duracion,
    this.detalle,
    this.item,
    this.logro,
    this.mision,
  });

  /// Paso del recibo que la origina.
  final PasoCelebracion paso;

  /// Overlay o chip.
  final FormatoCelebracion formato;

  /// Recibo completo, por si la pantalla necesita más contexto.
  final ReciboRecompensas recibo;

  /// Titular ("¡2 días seguidos!", "Nivel 4", "Nuevo equipamiento").
  final String titulo;

  /// Línea de apoyo.
  final String? detalle;

  /// Cuánto dura su animación. Nunca supera [ColaCelebraciones.limiteBloqueo]
  /// y es cero cuando el sistema pide reducir movimiento.
  final Duration duracion;

  /// Ítem entregado, cuando el paso es [PasoCelebracion.item].
  final ItemRecibo? item;

  /// Logro desbloqueado, cuando el paso es [PasoCelebracion.logro].
  final LogroRecibo? logro;

  /// Misión cumplida, cuando el paso es [PasoCelebracion.mision].
  final MisionRecibo? mision;

  /// Datos de racha, solo en el overlay de racha.
  RachaRecibo? get racha =>
      paso == PasoCelebracion.racha ? recibo.racha : null;

  /// Datos de nivel, solo en el overlay de subida de nivel.
  NivelRecibo? get nivel =>
      paso == PasoCelebracion.subidaNivel ? recibo.nivel : null;

  /// Rareza del ítem traducida al token visual.
  Rareza get rarezaVisual =>
      item == null ? Rareza.comun : Rareza.desdeApi(item!.rareza.api);

  /// ¿Se pinta a pantalla completa?
  bool get esOverlay => formato == FormatoCelebracion.overlay;

  /// Texto del botón que cierra la celebración.
  String get textoAccion => switch (paso) {
        PasoCelebracion.item =>
          (item?.puedeEquipar ?? false) ? 'Equipar ahora' : 'Guardar en el Vestidor',
        PasoCelebracion.subidaNivel => 'Seguir',
        _ => 'Continuar',
      };

  /// Etiqueta para el lector de pantalla.
  String get semantica =>
      detalle == null ? titulo : '$titulo. $detalle';
}

/// Cola ordenada de celebraciones.
class ColaCelebraciones extends ChangeNotifier {
  ColaCelebraciones({bool movimientoReducido = false})
      : _movimientoReducido = movimientoReducido;

  /// Tope duro: ninguna celebración retiene al usuario más que esto.
  static const Duration limiteBloqueo = Movimiento.celebracionLarga;

  final List<Celebracion> _cola = <Celebracion>[];
  List<Celebracion> _chips = const <Celebracion>[];
  ReciboRecompensas? _ultimoRecibo;
  Timer? _reloj;
  bool _listaParaContinuar = true;
  bool _movimientoReducido;

  /// Celebración que toca mostrar, o `null` si no queda ninguna.
  Celebracion? get actual => _cola.isEmpty ? null : _cola.first;

  /// ¿Hay algo encolado?
  bool get hayPendientes => _cola.isNotEmpty;

  /// Cuántas quedan por mostrar, contando la actual.
  int get pendientes => _cola.length;

  /// Chips del último recibo, para la pantalla de resumen.
  List<Celebracion> get chips => List<Celebracion>.unmodifiable(_chips);

  /// Último recibo encolado; P10 y P12 lo usan para el desglose.
  ReciboRecompensas? get ultimoRecibo => _ultimoRecibo;

  /// `true` cuando la animación de la celebración actual ya cumplió su tiempo.
  /// La pantalla puede habilitar su CTA; el toque, en cambio, funciona
  /// siempre.
  bool get listaParaContinuar => _listaParaContinuar;

  /// ¿Se están usando versiones estáticas?
  bool get movimientoReducido => _movimientoReducido;

  /// El armazón lo sincroniza con `reducirMovimiento(context)`.
  set movimientoReducido(bool valor) {
    if (_movimientoReducido == valor) return;
    _movimientoReducido = valor;
    if (valor) {
      _reloj?.cancel();
      _reloj = null;
      _listaParaContinuar = true;
    }
    notifyListeners();
  }

  /// Convierte un recibo en celebraciones y las encola.
  ///
  /// Si el recibo no trae nada que celebrar no ocurre nada. Los chips del
  /// recibo anterior se reemplazan por los de este.
  void encolar(ReciboRecompensas? recibo) {
    if (recibo == null || recibo.estaVacio) return;
    _ultimoRecibo = recibo;
    _chips = _construirChips(recibo);
    final List<Celebracion> nuevos = _construirOverlays(recibo);
    if (nuevos.isEmpty) {
      notifyListeners();
      return;
    }
    final bool estabaVacia = _cola.isEmpty;
    _cola.addAll(nuevos);
    if (estabaVacia) {
      _activar();
    } else {
      notifyListeners();
    }
  }

  /// Cierra la celebración visible y pasa a la siguiente.
  void descartar() {
    if (_cola.isEmpty) return;
    _cola.removeAt(0);
    if (_cola.isEmpty) {
      _reloj?.cancel();
      _reloj = null;
      _listaParaContinuar = true;
      notifyListeners();
      return;
    }
    _activar();
  }

  /// Salta la animación sin cerrar la celebración: el CTA queda disponible y
  /// las cifras deben pintarse ya en su valor final.
  void saltarAnimacion() {
    if (_listaParaContinuar) return;
    _reloj?.cancel();
    _reloj = null;
    _listaParaContinuar = true;
    notifyListeners();
  }

  /// Vacía la cola (por ejemplo, al cerrar sesión o al salir del resumen).
  void vaciar() {
    _reloj?.cancel();
    _reloj = null;
    _cola.clear();
    _chips = const <Celebracion>[];
    _ultimoRecibo = null;
    _listaParaContinuar = true;
    notifyListeners();
  }

  @override
  void dispose() {
    _reloj?.cancel();
    _reloj = null;
    super.dispose();
  }

  // -------------------------------------------------------------------------
  // Interno
  // -------------------------------------------------------------------------

  void _activar() {
    _reloj?.cancel();
    final Celebracion? siguiente = actual;
    if (siguiente == null) {
      _listaParaContinuar = true;
      notifyListeners();
      return;
    }
    if (_movimientoReducido || siguiente.duracion == Duration.zero) {
      _reloj = null;
      _listaParaContinuar = true;
      notifyListeners();
      return;
    }
    _listaParaContinuar = false;
    notifyListeners();
    _reloj = Timer(siguiente.duracion, () {
      _reloj = null;
      _listaParaContinuar = true;
      notifyListeners();
    });
  }

  Duration _duracion(Duration propuesta) {
    if (_movimientoReducido) return Duration.zero;
    return propuesta > limiteBloqueo ? limiteBloqueo : propuesta;
  }

  /// Overlays en el orden que manda `presentation_order` (máximo tres).
  List<Celebracion> _construirOverlays(ReciboRecompensas r) {
    final List<Celebracion> salida = <Celebracion>[];
    for (final PasoCelebracion paso in r.overlays) {
      final Celebracion? c = switch (paso) {
        PasoCelebracion.racha => _deRacha(r),
        PasoCelebracion.subidaNivel => _deNivel(r),
        PasoCelebracion.item => _deItem(r),
        _ => null,
      };
      if (c != null) salida.add(c);
    }
    return salida;
  }

  Celebracion? _deRacha(ReciboRecompensas r) {
    final RachaRecibo? racha = r.racha;
    if (racha == null || !racha.esPrimeraActividadDelDia) return null;
    final String titulo = racha.actual <= 1
        ? '¡Día 1 de tu racha!'
        : '¡${racha.actual} días seguidos!';
    final HitoRacha? hito = racha.hito;
    final String detalle = hito != null
        ? 'Hito alcanzado: ${hito.titulo}'
        : (racha.mejor > racha.actual
            ? 'Tu mejor marca son ${racha.mejor} días. Vas por ella.'
            : 'La constancia es tu mejor arma.');
    return Celebracion(
      paso: PasoCelebracion.racha,
      formato: FormatoCelebracion.overlay,
      recibo: r,
      titulo: titulo,
      detalle: detalle,
      duracion: _duracion(Movimiento.celebracion),
    );
  }

  Celebracion? _deNivel(ReciboRecompensas r) {
    final NivelRecibo? nivel = r.nivel;
    if (nivel == null || !nivel.subioNivel) return null;
    // Si se cruzaron varios niveles de una vez se muestra solo el final.
    final String titulo = 'Nivel ${nivel.despues}';
    final List<String> lineas = <String>[
      if ((nivel.tituloRangoDespues ?? '').isNotEmpty) nivel.tituloRangoDespues!,
      if (nivel.oroBonus > 0) '+${nivel.oroBonus} de oro',
      if (nivel.rarezasDesbloqueadas.isNotEmpty)
        'Nuevas rarezas en el Mercado',
    ];
    return Celebracion(
      paso: PasoCelebracion.subidaNivel,
      formato: FormatoCelebracion.overlay,
      recibo: r,
      titulo: titulo,
      detalle: lineas.isEmpty ? null : lineas.join(' · '),
      duracion: _duracion(Movimiento.celebracionLarga),
    );
  }

  Celebracion? _deItem(ReciboRecompensas r) {
    final ItemRecibo? item = r.itemDestacado;
    if (item == null) return null;
    final String motivo = item.motivoDesbloqueo ?? item.origen.etiqueta;
    return Celebracion(
      paso: PasoCelebracion.item,
      formato: FormatoCelebracion.overlay,
      recibo: r,
      titulo: item.nombre,
      detalle: '${item.rareza.etiqueta} · $motivo',
      duracion: _duracion(Movimiento.celebracion),
      item: item,
    );
  }

  /// Todo lo que no es overlay se entrega como chip para P10/P12.
  List<Celebracion> _construirChips(ReciboRecompensas r) {
    final List<Celebracion> salida = <Celebracion>[];

    for (final PasoCelebracion paso in r.chips) {
      switch (paso) {
        case PasoCelebracion.xp:
          final XpRecibo? xp = r.xp;
          if (xp == null) break;
          salida.add(
            _chip(
              r,
              paso,
              '+${xp.cantidad} XP',
              xp.motivoLegible.isEmpty ? null : xp.motivoLegible,
            ),
          );
        case PasoCelebracion.oro:
          final OroRecibo? oro = r.oro;
          if (oro == null) break;
          salida.add(_chip(r, paso, '+${oro.cantidad} de oro', null));
        case PasoCelebracion.dominio:
          final DeltaDominio? dominio = r.dominioDelTema;
          final ConocimientoRecibo? saber = r.conocimiento;
          if (dominio != null) {
            salida.add(
              _chip(
                r,
                paso,
                'Dominio ${dominio.nombre}',
                '${dominio.antes.round()} % → ${dominio.despues.round()} %',
              ),
            );
          } else if (saber != null) {
            salida.add(
              _chip(
                r,
                paso,
                'Dominio ${saber.nombre}',
                '${saber.dominioAntes.round()} % → '
                    '${saber.dominioDespues.round()} %',
              ),
            );
          }
        case PasoCelebracion.logro:
          for (final LogroRecibo logro in r.logros) {
            salida.add(
              Celebracion(
                paso: paso,
                formato: FormatoCelebracion.chip,
                recibo: r,
                titulo: 'Logro: ${logro.nombre}',
                detalle: logro.recompensa.estaVacia
                    ? logro.descripcion
                    : logro.recompensa.resumen,
                duracion: _duracion(Movimiento.corta),
                logro: logro,
              ),
            );
          }
        case PasoCelebracion.mision:
          for (final MisionRecibo mision in r.misionesCumplidas) {
            salida.add(
              Celebracion(
                paso: paso,
                formato: FormatoCelebracion.chip,
                recibo: r,
                titulo: 'Misión cumplida: ${mision.titulo}',
                detalle: mision.recompensa.estaVacia
                    ? null
                    : mision.recompensa.resumen,
                duracion: _duracion(Movimiento.corta),
                mision: mision,
              ),
            );
          }
        case PasoCelebracion.racha:
        case PasoCelebracion.subidaNivel:
        case PasoCelebracion.item:
          // Estos pasos solo llegan a chips si no cupieron entre los tres
          // overlays; se muestran resumidos.
          salida.add(_chip(r, paso, paso.etiqueta, null));
      }
    }

    // Los ítems que no encabezaron el overlay también merecen su chip.
    if (r.items.length > 1) {
      for (final ItemRecibo extra in r.items.skip(1)) {
        salida.add(
          Celebracion(
            paso: PasoCelebracion.item,
            formato: FormatoCelebracion.chip,
            recibo: r,
            titulo: extra.nombre,
            detalle: extra.rareza.etiqueta,
            duracion: _duracion(Movimiento.corta),
            item: extra,
          ),
        );
      }
    }

    return List<Celebracion>.unmodifiable(salida);
  }

  Celebracion _chip(
    ReciboRecompensas r,
    PasoCelebracion paso,
    String titulo,
    String? detalle,
  ) =>
      Celebracion(
        paso: paso,
        formato: FormatoCelebracion.chip,
        recibo: r,
        titulo: titulo,
        detalle: detalle,
        duracion: _duracion(Movimiento.corta),
      );
}
