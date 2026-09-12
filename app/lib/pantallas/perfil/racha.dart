/// P18 — Racha y calendario: hacer visible la constancia.
///
/// Racha actual y mejor marca, el mes entero con el estado de cada día, el
/// próximo hito con su recompensa y el objetivo diario con su intensidad. Los
/// días, los hitos y las recompensas los decide el Reino; la pantalla solo los
/// presenta y ofrece cambiar el objetivo.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../data/errores.dart';
import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/gamificacion.dart';
import '../../navegacion/rutas.dart';
import '../personaje/widgets/piezas.dart';

/// Configuración pública del juego (`GET /config`), de donde salen las
/// opciones de intensidad del objetivo diario.
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
}

/// Pantalla de Racha.
class PantallaRacha extends StatelessWidget {
  const PantallaRacha({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider<ControladorConfigJuego>(
      create: (BuildContext ctx) =>
          ControladorConfigJuego(ctx.read<Repositorios>())..cargar(),
      child: const _VistaRacha(),
    );
  }
}

class _VistaRacha extends StatefulWidget {
  const _VistaRacha();

  @override
  State<_VistaRacha> createState() => _VistaRachaState();
}

class _VistaRachaState extends State<_VistaRacha> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      context.read<ControladorGamificacion>().cargarRacha();
    });
  }

  @override
  Widget build(BuildContext context) {
    final ControladorGamificacion juego =
        context.watch<ControladorGamificacion>();
    final Racha racha = juego.racha;
    final CalendarioRacha? calendario = juego.calendario;

    final bool vacio = calendario == null && racha.estaVacia;

    return PantallaAtenea(
      titulo: 'Racha',
      mostrarVolver: true,
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        0,
        Espacio.md,
        Espacio.xl,
      ),
      cuerpo: RefreshIndicator(
        onRefresh: () => juego.cargarRacha(forzar: true),
        child: juego.cargandoRacha && vacio
            ? ListView(
                padding: EdgeInsets.zero,
                children: const <Widget>[
                  SizedBox(height: Espacio.md),
                  Esqueleto(alto: 150, radio: Redondeo.tarjeta),
                  SizedBox(height: Espacio.md),
                  Esqueleto(alto: 280, radio: Redondeo.tarjeta),
                  SizedBox(height: Espacio.md),
                  EsqueletoFilas(filas: 2, alto: 96),
                ],
              )
            : juego.errorRacha != null && vacio
                ? ListView(
                    padding: EdgeInsets.zero,
                    children: <Widget>[
                      const SizedBox(height: Espacio.xxl),
                      EstadoError(
                        titulo: 'No pudimos leer tu racha',
                        mensaje: juego.errorRacha!.mensaje,
                        alReintentar: () => juego.cargarRacha(forzar: true),
                      ),
                    ],
                  )
                : ListView(
                    padding: EdgeInsets.zero,
                    children: <Widget>[
                      if (juego.errorRacha != null)
                        BandaAviso(
                          icono: Icons.wifi_off_rounded,
                          mensaje:
                              'Mostramos tu última racha guardada.',
                          textoAccion: 'Reintentar',
                          alTocarAccion: () =>
                              juego.cargarRacha(forzar: true),
                        ),
                      const SizedBox(height: Espacio.xs),
                      _Llama(racha: racha),
                      const EncabezadoSeccion(titulo: 'Tu mes'),
                      _Calendario(
                        calendario: calendario,
                        mes: juego.mesCalendario,
                        cargando: juego.cargandoRacha,
                        alCambiarMes: juego.cambiarMes,
                      ),
                      if (racha.proximoHito != null) ...<Widget>[
                        const EncabezadoSeccion(titulo: 'Próximo hito'),
                        _Hito(hito: racha.proximoHito!, racha: racha),
                      ],
                      const EncabezadoSeccion(
                        titulo: 'Objetivo diario',
                        subtitulo:
                            'Cualquier actividad cuenta: lecciones, repasos y '
                            'desafíos',
                      ),
                      const _Objetivo(),
                      const SizedBox(height: Espacio.md),
                      const _FilaRecordatorio(),
                    ],
                  ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Llama
// ---------------------------------------------------------------------------

class _Llama extends StatelessWidget {
  const _Llama({required this.racha});

  final Racha racha;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool quieto = reducirMovimiento(context);
    final double intensidad = (racha.actual / 30).clamp(0.15, 1).toDouble();
    final double tamano = 56 + 36 * intensidad;
    final bool seRompio = racha.ultimoCambio == CambioRacha.rota;

    return TarjetaAtenea(
      elevada: true,
      colorBorde: p.brasa.withValues(alpha: 0.45),
      brillo: quieto ? 0 : 10 * intensidad,
      semantica: racha.actual == 0
          ? 'Sin racha activa. Tu mejor marca es ${racha.mejor} días'
          : 'Racha de ${racha.actual} días. Mejor marca ${racha.mejor} días',
      hijo: Column(
        children: <Widget>[
          Icon(
            Icons.local_fire_department_rounded,
            size: tamano,
            color: racha.actual == 0
                ? p.textoSecundario.withValues(alpha: 0.5)
                : p.brasa,
          ),
          const SizedBox(height: Espacio.xs),
          if (racha.actual == 0)
            Text(
              'Hoy es un buen día para empezar',
              textAlign: TextAlign.center,
              style: context.textos.headlineSmall,
            )
          else
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: <Widget>[
                CifraAnimada(
                  valor: racha.actual,
                  estilo: Cifras.heroe(context).copyWith(color: p.brasa),
                ),
                const SizedBox(width: Espacio.xs),
                Text(
                  racha.actual == 1 ? 'día' : 'días',
                  style: context.textos.titleLarge?.copyWith(
                    color: p.textoSecundario,
                  ),
                ),
              ],
            ),
          const SizedBox(height: Espacio.xs),
          Wrap(
            spacing: Espacio.xs,
            runSpacing: Espacio.xxs,
            alignment: WrapAlignment.center,
            children: <Widget>[
              Pildora(
                texto: 'Mejor racha: ${racha.mejor}',
                icono: Icons.emoji_events_rounded,
                color: p.oro,
              ),
              Pildora(
                texto: racha.estadoDia.etiqueta,
                icono: racha.hoyCuenta
                    ? Icons.check_circle_rounded
                    : Icons.hourglass_bottom_rounded,
                color: racha.hoyCuenta ? p.exito : p.textoSecundario,
              ),
              if (racha.graciaDisponible)
                Pildora(
                  texto: 'Día de gracia disponible',
                  icono: Icons.shield_rounded,
                  color: p.info,
                ),
            ],
          ),
          if (seRompio) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            BandaAviso(
              icono: Icons.restart_alt_rounded,
              color: p.info,
              mensaje: 'Tu racha se reinició. Tu mejor marca sigue siendo '
                  '${racha.mejor} días, y hoy empieza una nueva.',
            ),
          ],
          if (!racha.hoyCuenta && racha.actual > 0) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            BotonPrimario(
              texto: 'Cuidar mi racha hoy',
              subtitulo: 'Una lección corta basta',
              icono: Icons.play_arrow_rounded,
              alTocar: () => context.go(Rutas.inicio),
            ),
          ],
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Calendario
// ---------------------------------------------------------------------------

class _Calendario extends StatelessWidget {
  const _Calendario({
    required this.calendario,
    required this.mes,
    required this.cargando,
    required this.alCambiarMes,
  });

  final CalendarioRacha? calendario;
  final String? mes;
  final bool cargando;
  final Future<void> Function(String mes) alCambiarMes;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final DateTime referencia = _mesComoFecha(calendario?.mes ?? mes);
    final DateTime hoy = DateTime.now();
    final bool hayFuturo = !(referencia.year == hoy.year &&
        referencia.month == hoy.month);

    final int diasDelMes =
        DateTime(referencia.year, referencia.month + 1, 0).day;
    final int desplazamiento =
        DateTime(referencia.year, referencia.month, 1).weekday - 1;

    return TarjetaAtenea(
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              IconButton(
                icon: const Icon(Icons.chevron_left_rounded),
                tooltip: 'Mes anterior',
                onPressed: cargando
                    ? null
                    : () => alCambiarMes(
                          _comoClave(
                            DateTime(referencia.year, referencia.month - 1),
                          ),
                        ),
              ),
              Expanded(
                child: Text(
                  '${nombreDeMes(referencia.month)} ${referencia.year}',
                  textAlign: TextAlign.center,
                  style: context.textos.titleLarge,
                ),
              ),
              IconButton(
                icon: const Icon(Icons.chevron_right_rounded),
                tooltip: 'Mes siguiente',
                onPressed: cargando || !hayFuturo
                    ? null
                    : () => alCambiarMes(
                          _comoClave(
                            DateTime(referencia.year, referencia.month + 1),
                          ),
                        ),
              ),
            ],
          ),
          const SizedBox(height: Espacio.xs),
          Row(
            children: <Widget>[
              for (final String inicial in inicialesDeDia)
                Expanded(
                  child: Text(
                    inicial,
                    textAlign: TextAlign.center,
                    style: context.textos.bodySmall?.copyWith(
                      color: p.textoSecundario,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: Espacio.xs),
          GridView.builder(
            padding: EdgeInsets.zero,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 7,
              mainAxisSpacing: Espacio.xxs,
              crossAxisSpacing: Espacio.xxs,
            ),
            itemCount: desplazamiento + diasDelMes,
            itemBuilder: (BuildContext context, int i) {
              if (i < desplazamiento) return const SizedBox.shrink();
              final int numero = i - desplazamiento + 1;
              final DateTime fecha =
                  DateTime(referencia.year, referencia.month, numero);
              return _CeldaDia(
                fecha: fecha,
                dia: calendario?.porFecha(fecha),
                esHoy: fecha.year == hoy.year &&
                    fecha.month == hoy.month &&
                    fecha.day == hoy.day,
              );
            },
          ),
          const SizedBox(height: Espacio.sm),
          const _LeyendaCalendario(),
          if (calendario != null) ...<Widget>[
            const SizedBox(height: Espacio.xs),
            FilaDato(
              etiqueta: 'Días activos este mes',
              valor: '${calendario!.diasActivos}',
              icono: Icons.calendar_month_rounded,
            ),
            if (calendario!.mejorLongitud > 0)
              FilaDato(
                etiqueta: 'Mejor seguidilla del mes',
                valor: '${calendario!.mejorLongitud} días',
                icono: Icons.trending_up_rounded,
              ),
          ],
        ],
      ),
    );
  }

  static DateTime _mesComoFecha(String? clave) {
    final DateTime hoy = DateTime.now();
    if (clave == null || !clave.contains('-')) {
      return DateTime(hoy.year, hoy.month);
    }
    final List<String> partes = clave.split('-');
    final int? ano = int.tryParse(partes[0]);
    final int? mes = int.tryParse(partes[1]);
    if (ano == null || mes == null || mes < 1 || mes > 12) {
      return DateTime(hoy.year, hoy.month);
    }
    return DateTime(ano, mes);
  }

  static String _comoClave(DateTime fecha) =>
      '${fecha.year.toString().padLeft(4, '0')}-'
      '${fecha.month.toString().padLeft(2, '0')}';
}

class _CeldaDia extends StatelessWidget {
  const _CeldaDia({
    required this.fecha,
    required this.dia,
    required this.esHoy,
  });

  final DateTime fecha;
  final DiaRacha? dia;
  final bool esHoy;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final EstadoDia estado = dia?.estadoDia ?? EstadoDia.inactivo;
    final bool cuenta = estado.cuentaParaRacha;

    final Color fondo = switch (estado) {
      EstadoDia.activo => p.brasa,
      EstadoDia.gracia => p.info.withValues(alpha: 0.22),
      EstadoDia.viaje => p.dominio.withValues(alpha: 0.22),
      EstadoDia.inactivo => Colors.transparent,
    };
    final Color texto = estado == EstadoDia.activo
        ? p.sobreOro
        : (cuenta ? p.textoPrimario : p.textoSecundario);

    final IconData? marca = switch (estado) {
      EstadoDia.gracia => Icons.shield_rounded,
      EstadoDia.viaje => Icons.flight_rounded,
      _ => null,
    };

    final List<String> descripcion = <String>[
      '${nombresDeDia[(fecha.weekday - 1).clamp(0, 6)]} ${fecha.day}',
      estado.etiqueta,
      if (dia != null && dia!.minutos > 0) '${dia!.minutos} minutos',
      if (dia?.objetivoCumplido ?? false) 'objetivo cumplido',
      if (esHoy) 'hoy',
    ];

    return Semantics(
      label: descripcion.join(', '),
      excludeSemantics: true,
      child: Tooltip(
        message: descripcion.join(' · '),
        child: AnimatedContainer(
          duration: Movimiento.micro,
          decoration: BoxDecoration(
            color: fondo,
            shape: BoxShape.circle,
            border: Border.all(
              color: esHoy
                  ? p.arcano
                  : (cuenta ? p.brasa.withValues(alpha: 0.5) : p.borde),
              width: esHoy ? 2 : 1,
            ),
          ),
          child: Stack(
            alignment: Alignment.center,
            children: <Widget>[
              Text(
                '${fecha.day}',
                style: Cifras.pequena(context).copyWith(color: texto),
              ),
              if (marca != null)
                Positioned(
                  bottom: 2,
                  child: Icon(marca, size: 9, color: p.textoSecundario),
                ),
              if (dia?.objetivoCumplido ?? false)
                Positioned(
                  top: 1,
                  right: 3,
                  child: Icon(Icons.star_rounded, size: 9, color: p.oro),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LeyendaCalendario extends StatelessWidget {
  const _LeyendaCalendario();

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Wrap(
      spacing: Espacio.xs,
      runSpacing: Espacio.xxs,
      children: <Widget>[
        Pildora(
          texto: 'Día activo',
          icono: Icons.local_fire_department_rounded,
          color: p.brasa,
        ),
        Pildora(texto: 'Gracia', icono: Icons.shield_rounded, color: p.info),
        Pildora(texto: 'Viaje', icono: Icons.flight_rounded, color: p.dominio),
        Pildora(texto: 'Objetivo cumplido', icono: Icons.star_rounded, color: p.oro),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Próximo hito
// ---------------------------------------------------------------------------

class _Hito extends StatelessWidget {
  const _Hito({required this.hito, required this.racha});

  final HitoRacha hito;
  final Racha racha;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final double fraccion =
        hito.dias <= 0 ? 0 : (racha.actual / hito.dias).clamp(0, 1).toDouble();
    final String recompensa = hito.recompensa?.resumen ?? '';

    return TarjetaAtenea(
      colorBorde: p.oro.withValues(alpha: 0.4),
      semantica: 'Próximo hito a los ${hito.dias} días. '
          'Te faltan ${hito.faltan}. $recompensa',
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(Icons.flag_rounded, color: p.oro),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Text(
                  hito.titulo ?? '${hito.dias} días seguidos',
                  style: context.textos.titleLarge,
                ),
              ),
              Pildora(
                texto: hito.faltan <= 0
                    ? '¡Es hoy!'
                    : (hito.faltan == 1 ? 'Falta 1 día' : 'Faltan ${hito.faltan} días'),
                color: p.oro,
              ),
            ],
          ),
          const SizedBox(height: Espacio.sm),
          BarraProgreso(
            valor: fraccion,
            color: p.oro,
            etiqueta: 'Tu avance hacia el hito',
            textoDerecha: '${racha.actual} / ${hito.dias}',
          ),
          if (recompensa.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            Row(
              children: <Widget>[
                Icon(Icons.card_giftcard_rounded, size: 18, color: p.oro),
                const SizedBox(width: Espacio.xs),
                Expanded(
                  child: Text(
                    recompensa,
                    style: context.textos.bodyLarge?.copyWith(color: p.oro),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Objetivo diario
// ---------------------------------------------------------------------------

class _Objetivo extends StatefulWidget {
  const _Objetivo();

  @override
  State<_Objetivo> createState() => _ObjetivoState();
}

class _ObjetivoState extends State<_Objetivo> {
  TipoObjetivo? _tipoElegido;

  Future<void> _guardar(TipoObjetivo tipo, int meta) async {
    final ControladorGamificacion juego =
        context.read<ControladorGamificacion>();
    final bool listo = await juego.cambiarObjetivo(tipo: tipo, meta: meta);
    if (!mounted) return;
    avisar(
      context,
      listo
          ? 'Objetivo guardado: $meta ${tipo.unidad} al día.'
          : juego.errorRacha?.mensaje ?? 'No pudimos guardar el objetivo.',
      esError: !listo,
    );
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final ControladorGamificacion juego =
        context.watch<ControladorGamificacion>();
    final ControladorConfigJuego config =
        context.watch<ControladorConfigJuego>();
    final ObjetivoDiario objetivo = juego.objetivoDiario;
    final TipoObjetivo tipo = _tipoElegido ?? objetivo.tipo;
    final List<int> opciones = config.opcionesDe(tipo);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (juego.recomendacion != null)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.sm),
            child: _Recomendacion(recomendacion: juego.recomendacion!),
          ),
        TarjetaAtenea(
          hijo: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Icon(Icons.track_changes_rounded, color: p.arcano),
                  const SizedBox(width: Espacio.xs),
                  Expanded(
                    child: Text(
                      'Hoy: ${objetivo.metaLegible}',
                      style: context.textos.titleLarge,
                    ),
                  ),
                  if (objetivo.cumplido)
                    Pildora(
                      texto: 'Cumplido',
                      icono: Icons.check_circle_rounded,
                      color: p.exito,
                    ),
                ],
              ),
              const SizedBox(height: Espacio.sm),
              BarraProgreso(
                valor: objetivo.fraccion,
                color: objetivo.cumplido ? p.exito : p.arcano,
                etiqueta: 'Progreso de hoy',
                textoDerecha:
                    '${objetivo.progreso} / ${objetivo.meta} ${tipoUnidad(objetivo.tipo)}',
              ),
              if (!objetivo.cumplido && objetivo.restante > 0) ...<Widget>[
                const SizedBox(height: Espacio.xs),
                Text(
                  'Te faltan ${objetivo.restante} ${tipoUnidad(objetivo.tipo)} '
                  'para cerrar el día.',
                  style: context.textos.bodyMedium?.copyWith(
                    color: p.textoSecundario,
                  ),
                ),
              ],
              if (objetivo.oroBonus > 0) ...<Widget>[
                const SizedBox(height: Espacio.xs),
                Row(
                  children: <Widget>[
                    Icon(
                      Icons.monetization_on_rounded,
                      size: 18,
                      color: p.oro,
                    ),
                    const SizedBox(width: Espacio.xs),
                    Expanded(
                      child: Text(
                        'Cumplirlo suma ${objetivo.oroBonus} de oro.',
                        style: context.textos.bodyMedium?.copyWith(
                          color: p.oro,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
              if (objetivo.tieneCambioPendiente) ...<Widget>[
                const SizedBox(height: Espacio.sm),
                BandaAviso(
                  icono: Icons.schedule_rounded,
                  color: p.info,
                  mensaje:
                      'Tu nuevo objetivo empieza mañana; hoy sigue vigente el '
                      'de siempre.',
                ),
              ],
              const SizedBox(height: Espacio.md),
              Text('Cambiar el objetivo', style: context.textos.titleMedium),
              const SizedBox(height: Espacio.xs),
              Wrap(
                spacing: Espacio.xs,
                runSpacing: Espacio.xxs,
                children: <Widget>[
                  for (final TipoObjetivo t in TipoObjetivo.values)
                    ChoiceChip(
                      selected: t == tipo,
                      showCheckmark: false,
                      label: Text(t.etiqueta),
                      labelStyle: context.textos.bodySmall?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: t == tipo ? p.textoPrimario : p.textoSecundario,
                      ),
                      selectedColor: p.arcano.withValues(alpha: 0.18),
                      side: BorderSide(color: t == tipo ? p.arcano : p.borde),
                      materialTapTargetSize: MaterialTapTargetSize.padded,
                      onSelected: juego.guardandoObjetivo
                          ? null
                          : (bool _) => setState(() => _tipoElegido = t),
                    ),
                ],
              ),
              const SizedBox(height: Espacio.sm),
              if (opciones.isEmpty)
                Text(
                  'Las intensidades llegan del Reino. Vuelve a intentarlo en '
                  'un momento.',
                  style: context.textos.bodyMedium?.copyWith(
                    color: p.textoSecundario,
                  ),
                )
              else
                Wrap(
                  spacing: Espacio.xs,
                  runSpacing: Espacio.xs,
                  children: <Widget>[
                    for (int i = 0; i < opciones.length; i++)
                      _OpcionMeta(
                        etiqueta: _intensidad(i, opciones.length),
                        meta: opciones[i],
                        unidad: tipoUnidad(tipo),
                        activa: tipo == objetivo.tipo &&
                            opciones[i] == objetivo.meta,
                        deshabilitada: juego.guardandoObjetivo,
                        alTocar: () => _guardar(tipo, opciones[i]),
                      ),
                  ],
                ),
              const SizedBox(height: Espacio.xs),
              Text(
                'Subir el listón rige hoy mismo; bajarlo empieza mañana.',
                style: context.textos.bodySmall?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  static String _intensidad(int indice, int total) {
    if (total <= 1) return 'Único';
    if (indice == 0) return 'Ligero';
    if (indice == total - 1) return 'Intenso';
    if (indice == 1) return 'Normal';
    return 'Exigente';
  }
}

/// Unidad del objetivo, para acompañar siempre al número.
String tipoUnidad(TipoObjetivo tipo) => tipo.unidad;

class _OpcionMeta extends StatelessWidget {
  const _OpcionMeta({
    required this.etiqueta,
    required this.meta,
    required this.unidad,
    required this.activa,
    required this.deshabilitada,
    required this.alTocar,
  });

  final String etiqueta;
  final int meta;
  final String unidad;
  final bool activa;
  final bool deshabilitada;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color acento = activa ? p.arcano : p.borde;

    return Semantics(
      label: '$etiqueta, $meta $unidad al día',
      selected: activa,
      button: true,
      excludeSemantics: true,
      child: Material(
        color: activa ? p.arcano.withValues(alpha: 0.16) : p.superficie,
        borderRadius: Redondeo.rBoton,
        child: InkWell(
          onTap: deshabilitada ? null : alTocar,
          borderRadius: Redondeo.rBoton,
          child: Container(
            constraints: const BoxConstraints(
              minHeight: Medida.areaTactilMin,
              minWidth: 92,
            ),
            padding: const EdgeInsets.symmetric(
              horizontal: Espacio.sm,
              vertical: Espacio.xs,
            ),
            decoration: BoxDecoration(
              borderRadius: Redondeo.rBoton,
              border: Border.all(color: acento, width: activa ? 1.8 : 1),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  etiqueta,
                  style: context.textos.bodySmall?.copyWith(
                    color: activa ? p.textoPrimario : p.textoSecundario,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                Text('$meta $unidad', style: Cifras.pequena(context)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Recomendacion extends StatelessWidget {
  const _Recomendacion({required this.recomendacion});

  final RecomendacionObjetivo recomendacion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final ControladorGamificacion juego =
        context.watch<ControladorGamificacion>();
    final String mensaje = recomendacion.mensaje ??
        (recomendacion.proponeSubir
            ? 'Llevas varios días cumpliendo con holgura. ¿Subimos a '
                '${recomendacion.metaSugerida} ${recomendacion.tipoSugerido.unidad}?'
            : 'Últimamente cuesta llegar. ¿Dejamos el objetivo en '
                '${recomendacion.metaSugerida} ${recomendacion.tipoSugerido.unidad}?');

    return TarjetaAtenea(
      elevada: true,
      colorBorde: p.info.withValues(alpha: 0.45),
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(Icons.tips_and_updates_rounded, color: p.info),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Text(
                  'El Reino te propone',
                  style: context.textos.titleMedium,
                ),
              ),
            ],
          ),
          const SizedBox(height: Espacio.xs),
          Text(mensaje, style: context.textos.bodyLarge),
          const SizedBox(height: Espacio.sm),
          Row(
            children: <Widget>[
              Expanded(
                child: FilledButton(
                  onPressed: juego.guardandoObjetivo
                      ? null
                      : juego.aceptarRecomendacion,
                  child: const Text('Aceptar'),
                ),
              ),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: OutlinedButton(
                  onPressed: juego.descartarRecomendacion,
                  child: const Text('Ahora no'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _FilaRecordatorio extends StatelessWidget {
  const _FilaRecordatorio();

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return TarjetaAtenea(
      alTocar: () => context.go(Rutas.ajustes),
      semantica: 'Recordatorio diario. Se configura en Ajustes',
      hijo: Row(
        children: <Widget>[
          Icon(Icons.notifications_active_rounded, color: p.arcano),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Recordatorio diario', style: context.textos.titleMedium),
                Text(
                  'Elige a qué hora te avisamos, en Ajustes',
                  style: context.textos.bodySmall?.copyWith(
                    color: p.textoSecundario,
                  ),
                ),
              ],
            ),
          ),
          Icon(Icons.chevron_right_rounded, color: p.textoSecundario),
        ],
      ),
    );
  }
}
