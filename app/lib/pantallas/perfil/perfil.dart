/// P17 — Perfil: quién soy y cuánto he progresado.
///
/// Se lee como una ficha de personaje de videojuego: el avatar con lo que
/// lleva puesto, el nivel y su rango, las seis estadísticas héroe, los
/// conocimientos con su dominio y los últimos siete días de estudio. Ningún
/// número se calcula aquí: todos vienen de `GET /profile`.
library;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../data/errores.dart';
import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/personaje.dart';
import '../../estado/sesion.dart';
import '../../navegacion/rutas.dart';
import '../personaje/widgets/avatar_capas.dart';
import '../personaje/widgets/piezas.dart';

/// Estado del perfil (§7.8 `GET /profile`).
///
/// Vive junto a la pantalla porque solo ella lo consume; la pantalla nunca
/// llama al repositorio directamente.
class ControladorPerfil extends ChangeNotifier {
  ControladorPerfil(this._repos);

  final Repositorios _repos;

  Perfil? _perfil;
  bool _cargando = false;
  ErrorAtenea? _error;

  /// Perfil completo, o `null` mientras no haya llegado.
  Perfil? get perfil => _perfil;

  /// Primera carga en curso.
  bool get cargando => _cargando;

  /// Último error.
  ErrorAtenea? get error => _error;

  /// ¿Hay algo que pintar?
  bool get hayDatos => _perfil != null;

  /// Trae el perfil; con [forzar] vuelve a pedirlo aunque ya esté en memoria.
  Future<void> cargar({bool forzar = false}) async {
    if (_cargando) return;
    if (!forzar && _perfil != null) return;
    _cargando = true;
    _error = null;
    notifyListeners();
    try {
      _perfil = await _repos.panel.perfil();
    } catch (e) {
      _error = e is ErrorAtenea
          ? e
          : const ErrorAtenea(
              codigo: 'inesperado',
              mensaje: 'Ocurrió algo inesperado. Inténtalo de nuevo.',
            );
    } finally {
      _cargando = false;
      notifyListeners();
    }
  }
}

/// Pantalla de Perfil.
class PantallaPerfil extends StatelessWidget {
  const PantallaPerfil({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider<ControladorPerfil>(
      create: (BuildContext ctx) =>
          ControladorPerfil(ctx.read<Repositorios>())..cargar(),
      child: const _VistaPerfil(),
    );
  }
}

class _VistaPerfil extends StatelessWidget {
  const _VistaPerfil();

  @override
  Widget build(BuildContext context) {
    final ControladorPerfil control = context.watch<ControladorPerfil>();
    final ControladorSesion sesion = context.watch<ControladorSesion>();
    final Perfil? perfil = control.perfil;

    return PantallaAtenea(
      titulo: 'Perfil',
      limitarAnchoLectura: false,
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        0,
        Espacio.md,
        Espacio.xl,
      ),
      acciones: <Widget>[
        IconButton(
          icon: const Icon(Icons.settings_rounded),
          tooltip: 'Ajustes',
          onPressed: () => context.go(Rutas.ajustes),
        ),
      ],
      cuerpo: RefreshIndicator(
        onRefresh: () => control.cargar(forzar: true),
        child: perfil == null
            ? _cuerpoSinDatos(context, control)
            : _cuerpo(context, control, perfil, sesion),
      ),
    );
  }

  Widget _cuerpoSinDatos(BuildContext context, ControladorPerfil control) {
    if (control.cargando) {
      return ListView(
        padding: EdgeInsets.zero,
        children: const <Widget>[
          SizedBox(height: Espacio.md),
          Esqueleto(alto: 180, radio: Redondeo.tarjeta),
          SizedBox(height: Espacio.md),
          EsqueletoFilas(filas: 2, alto: 84),
          SizedBox(height: Espacio.xs),
          EsqueletoFilas(filas: 2, alto: 64),
        ],
      );
    }
    return ListView(
      padding: EdgeInsets.zero,
      children: <Widget>[
        const SizedBox(height: Espacio.xxl),
        EstadoError(
          titulo: 'No pudimos abrir tu crónica',
          mensaje: control.error?.mensaje ??
              'Vuelve a intentarlo en un momento.',
          alReintentar: () => control.cargar(forzar: true),
        ),
      ],
    );
  }

  Widget _cuerpo(
    BuildContext context,
    ControladorPerfil control,
    Perfil perfil,
    ControladorSesion sesion,
  ) {
    final EstadisticasPerfil e = perfil.estadisticas;

    return ListView(
      padding: EdgeInsets.zero,
      children: <Widget>[
        if (control.error != null)
          BandaAviso(
            icono: Icons.wifi_off_rounded,
            mensaje: 'Estás viendo tu última crónica guardada.',
            textoAccion: 'Reintentar',
            alTocarAccion: () => control.cargar(forzar: true),
          ),
        const SizedBox(height: Espacio.xs),
        _Cabecera(perfil: perfil, sesion: sesion),
        const EncabezadoSeccion(titulo: 'Tus marcas'),
        _Estadisticas(estadisticas: e),
        const EncabezadoSeccion(
          titulo: 'Conocimientos',
          subtitulo: 'Tu dominio en cada territorio',
        ),
        _Conocimientos(areas: perfil.conocimientos),
        EncabezadoSeccion(
          titulo: 'Últimos 7 días',
          subtitulo: perfil.maximoMinutos == 0
              ? 'Aún no hay minutos que contar'
              : 'Minutos de estudio por día',
        ),
        _GraficoSemana(dias: perfil.ultimos7Dias),
        const EncabezadoSeccion(titulo: 'Más de ti'),
        _Accesos(logros: e.logrosDesbloqueados),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Cabecera: avatar, nivel y barra de XP
// ---------------------------------------------------------------------------

class _Cabecera extends StatelessWidget {
  const _Cabecera({required this.perfil, required this.sesion});

  final Perfil perfil;
  final ControladorSesion sesion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Personaje? heroe = perfil.personaje ?? sesion.personaje;
    final RasgosAvatar? rasgos =
        context.watch<ControladorPersonaje>().avatar?.rasgos;
    final int nivel = heroe?.nivel ?? 1;
    final double fraccion = ((heroe?.porcentajeProgreso ?? 0) / 100)
        .clamp(0, 1)
        .toDouble();

    return TarjetaAtenea(
      elevada: true,
      colorBorde: p.arcano.withValues(alpha: 0.5),
      hijo: Stack(
        children: <Widget>[
          Positioned(
            top: 0,
            left: 0,
            child: OrnamentoEsquina(color: p.oro.withValues(alpha: 0.7)),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: <Widget>[
                  AvatarCapas(
                    capas: perfil.capasAvatar,
                    rasgos: rasgos,
                    tamano: 124,
                    nombre: heroe?.nombre,
                  ),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          heroe?.nombre ?? sesion.nombreVisible,
                          style: context.textos.displaySmall,
                        ),
                        const SizedBox(height: Espacio.xxs),
                        Wrap(
                          spacing: Espacio.xs,
                          runSpacing: Espacio.xxs,
                          children: <Widget>[
                            Pildora(
                              texto: (heroe?.arquetipo ?? Arquetipo.acero)
                                  .etiqueta,
                              icono: Icons.auto_awesome_motion_rounded,
                              color: p.arcano,
                            ),
                            if (heroe != null)
                              Pildora(
                                texto: heroe.tituloRango,
                                icono: Icons.workspace_premium_rounded,
                                color: p.oro,
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: Espacio.md),
              Row(
                children: <Widget>[
                  Icon(Icons.shield_rounded, size: 20, color: p.arcano),
                  const SizedBox(width: Espacio.xs),
                  Text('Nivel $nivel', style: Cifras.media(context)),
                  const Spacer(),
                  Text(
                    heroe == null || heroe.xpParaSiguiente <= 0
                        ? 'XP ${cifra(heroe?.xpTotal ?? 0)}'
                        : 'Faltan ${cifra(heroe.xpParaSiguiente)} XP',
                    style: context.textos.bodyMedium?.copyWith(
                      color: p.textoSecundario,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: Espacio.xs),
              BarraProgreso(
                valor: fraccion,
                color: p.arcano,
                etiqueta: 'Progreso al nivel ${nivel + 1}',
                textoDerecha: '${(fraccion * 100).round()} %',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Las seis estadísticas héroe
// ---------------------------------------------------------------------------

class _Estadisticas extends StatelessWidget {
  const _Estadisticas({required this.estadisticas});

  final EstadisticasPerfil estadisticas;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;

    final List<Widget> fichas = <Widget>[
      FichaMedallon(
        tipo: Medallon.xp,
        valor: cifra(estadisticas.xpTotal),
        etiqueta: 'XP total',
      ),
      FichaMedallon(
        tipo: Medallon.racha,
        valor: '${estadisticas.rachaActual}',
        etiqueta: estadisticas.rachaActual == 1 ? 'Día seguido' : 'Días seguidos',
        alTocar: () => context.go(Rutas.racha),
      ),
      FichaMedallon(
        tipo: Medallon.tiempo,
        valor: estadisticas.tiempoLegible,
        etiqueta: 'Estudiadas',
      ),
      FichaMedallon(
        tipo: Medallon.dominio,
        valor: cifra(estadisticas.temasDominados),
        etiqueta: 'Temas dominados',
      ),
      FichaEstadistica(
        icono: Icons.military_tech_rounded,
        color: p.oro,
        valor: cifra(estadisticas.logrosDesbloqueados),
        etiqueta: 'Logros',
        alTocar: () => context.go(Rutas.logros),
      ),
      FichaEstadistica(
        icono: Icons.checkroom_rounded,
        color: p.dominio,
        valor: cifra(estadisticas.itemsPoseidos),
        etiqueta: 'Objetos',
        alTocar: () => context.go(Rutas.personaje),
      ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (estadisticas.estaVacio)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.sm),
            child: BandaAviso(
              icono: Icons.auto_stories_rounded,
              color: p.arcano,
              mensaje: 'Tu crónica empieza hoy. La primera lección ya cuenta.',
            ),
          ),
        GridView.count(
          padding: EdgeInsets.zero,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisCount: 3,
          mainAxisSpacing: Espacio.xs,
          crossAxisSpacing: Espacio.xs,
          childAspectRatio: 0.82,
          children: fichas,
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Conocimientos
// ---------------------------------------------------------------------------

class _Conocimientos extends StatelessWidget {
  const _Conocimientos({required this.areas});

  final List<AreaConocimiento> areas;

  @override
  Widget build(BuildContext context) {
    if (areas.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: Espacio.md),
        child: EstadoVacio(
          icono: Icons.explore_rounded,
          titulo: 'Ningún territorio explorado aún',
          mensaje:
              'Crea tu primera Ruta y este mapa empezará a llenarse de '
              'conocimientos con su propio nivel.',
          textoAccion: 'Empezar una aventura',
          alTocarAccion: () => context.go(Rutas.aventura),
        ),
      );
    }

    return Column(
      children: <Widget>[
        for (final AreaConocimiento area in areas)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.sm),
            child: _FilaConocimiento(area: area),
          ),
      ],
    );
  }
}

class _FilaConocimiento extends StatelessWidget {
  const _FilaConocimiento({required this.area});

  final AreaConocimiento area;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = colorDeDominio(context, area.estado);
    final double dominio = (area.dominio / 100).clamp(0, 1).toDouble();

    return TarjetaAtenea(
      semantica: '${area.nombre}. Nivel ${area.nivel}. '
          'Dominio ${area.dominio.round()} por ciento. ${area.estado.etiqueta}',
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                height: 36,
                width: 36,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.14),
                  borderRadius: Redondeo.rChip,
                ),
                child: Icon(Icons.terrain_rounded, size: 20, color: color),
              ),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(area.nombre, style: context.textos.titleMedium),
                    Text(
                      area.tituloRango == null
                          ? 'Nivel ${area.nivel}'
                          : '${area.tituloRango} · Nivel ${area.nivel}',
                      style: context.textos.bodySmall?.copyWith(
                        color: p.textoSecundario,
                      ),
                    ),
                  ],
                ),
              ),
              Text(
                tiempoLegible(area.segundosEstudio),
                style: Cifras.pequena(context),
              ),
            ],
          ),
          const SizedBox(height: Espacio.xs),
          BarraProgreso(
            valor: dominio,
            color: color,
            etiqueta: 'Dominio',
            textoDerecha: '${area.dominio.round()} %',
          ),
          const SizedBox(height: Espacio.xs),
          Pildora(
            texto: area.estado.etiqueta,
            icono: area.estado.pideRepaso
                ? Icons.history_rounded
                : Icons.psychology_rounded,
            color: color,
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Últimos siete días
// ---------------------------------------------------------------------------

class _GraficoSemana extends StatelessWidget {
  const _GraficoSemana({required this.dias});

  final List<DiaActividad> dias;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;

    if (dias.isEmpty) {
      return TarjetaAtenea(
        hijo: Padding(
          padding: const EdgeInsets.symmetric(vertical: Espacio.md),
          child: Text(
            'Cuando estudies, aquí verás cómo se reparte tu semana.',
            textAlign: TextAlign.center,
            style: context.textos.bodyMedium?.copyWith(
              color: p.textoSecundario,
            ),
          ),
        ),
      );
    }

    int maximo = 0;
    for (final DiaActividad d in dias) {
      if (d.minutos > maximo) maximo = d.minutos;
    }
    final double techo = (maximo == 0 ? 10 : maximo * 1.25).toDouble();

    final String descripcion = dias
        .map(
          (DiaActividad d) =>
              '${nombresDeDia[(d.fecha.weekday - 1).clamp(0, 6)]} '
              '${d.minutos} minutos',
        )
        .join(', ');

    return TarjetaAtenea(
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Semantics(
            label: 'Minutos de estudio por día: $descripcion',
            excludeSemantics: true,
            child: SizedBox(
              height: 168,
              child: BarChart(
                BarChartData(
                  alignment: BarChartAlignment.spaceAround,
                  maxY: techo,
                  minY: 0,
                  gridData: const FlGridData(show: false),
                  borderData: FlBorderData(show: false),
                  barTouchData: BarTouchData(enabled: false),
                  titlesData: FlTitlesData(
                    leftTitles: const AxisTitles(),
                    topTitles: const AxisTitles(),
                    rightTitles: const AxisTitles(),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 30,
                        getTitlesWidget: (double valor, TitleMeta meta) {
                          final int i = valor.round();
                          if (i < 0 || i >= dias.length) {
                            return const SizedBox.shrink();
                          }
                          final DiaActividad d = dias[i];
                          return Padding(
                            padding: const EdgeInsets.only(top: Espacio.xs),
                            child: Text(
                              inicialesDeDia[(d.fecha.weekday - 1).clamp(0, 6)],
                              style: context.textos.bodySmall?.copyWith(
                                color: d.objetivoCumplido
                                    ? p.oro
                                    : p.textoSecundario,
                                fontWeight: d.objetivoCumplido
                                    ? FontWeight.w800
                                    : FontWeight.w600,
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                  barGroups: <BarChartGroupData>[
                    for (int i = 0; i < dias.length; i++)
                      BarChartGroupData(
                        x: i,
                        barRods: <BarChartRodData>[
                          BarChartRodData(
                            toY: dias[i].minutos.toDouble(),
                            width: 18,
                            color: dias[i].objetivoCumplido ? p.oro : p.arcano,
                            borderRadius: const BorderRadius.vertical(
                              top: Radius.circular(Redondeo.chip),
                            ),
                            backDrawRodData: BackgroundBarChartRodData(
                              show: true,
                              toY: techo,
                              color: p.borde.withValues(alpha: 0.45),
                            ),
                          ),
                        ],
                      ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: Espacio.xs),
          Row(
            children: <Widget>[
              Container(
                height: 10,
                width: 10,
                decoration: BoxDecoration(
                  color: p.oro,
                  borderRadius: Redondeo.rPildora,
                ),
              ),
              const SizedBox(width: Espacio.xxs + 2),
              Text(
                'Días con objetivo cumplido',
                style: context.textos.bodySmall?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Accesos
// ---------------------------------------------------------------------------

class _Accesos extends StatelessWidget {
  const _Accesos({required this.logros});

  final int logros;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        _FilaAcceso(
          icono: Icons.local_fire_department_rounded,
          titulo: 'Racha y calendario',
          detalle: 'Tu constancia, día a día',
          color: context.paleta.brasa,
          alTocar: () => context.go(Rutas.racha),
        ),
        _FilaAcceso(
          icono: Icons.military_tech_rounded,
          titulo: 'Logros',
          detalle: '$logros desbloqueados',
          color: context.paleta.oro,
          alTocar: () => context.go(Rutas.logros),
        ),
        _FilaAcceso(
          icono: Icons.checkroom_rounded,
          titulo: 'Vestidor',
          detalle: 'Cambia tu aspecto y tu equipamiento',
          color: context.paleta.dominio,
          alTocar: () => context.go(Rutas.personaje),
        ),
        _FilaAcceso(
          icono: Icons.settings_rounded,
          titulo: 'Ajustes',
          detalle: 'Cuenta, apariencia y notificaciones',
          color: context.paleta.textoSecundario,
          alTocar: () => context.go(Rutas.ajustes),
        ),
      ],
    );
  }
}

class _FilaAcceso extends StatelessWidget {
  const _FilaAcceso({
    required this.icono,
    required this.titulo,
    required this.detalle,
    required this.color,
    required this.alTocar,
  });

  final IconData icono;
  final String titulo;
  final String detalle;
  final Color color;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.xs),
      child: TarjetaAtenea(
        alTocar: alTocar,
        padding: const EdgeInsets.symmetric(
          horizontal: Espacio.sm,
          vertical: Espacio.sm,
        ),
        semantica: '$titulo. $detalle',
        hijo: Row(
          children: <Widget>[
            Container(
              height: 40,
              width: 40,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.14),
                borderRadius: Redondeo.rChip,
              ),
              child: Icon(icono, size: 20, color: color),
            ),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(titulo, style: context.textos.titleMedium),
                  Text(
                    detalle,
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
      ),
    );
  }
}
