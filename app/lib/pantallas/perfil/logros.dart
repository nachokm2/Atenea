/// P20 · Logros: la sala de trofeos del héroe.
///
/// Cuadrícula de medallas con su estado (desbloqueada con fecha, en progreso
/// con su contador, o silueta con pista si es secreta), filtros por estado y
/// por categoría, y una hoja de detalle con los niveles del logro y lo que
/// entrega cada uno. Nada se calcula aquí: el progreso y las recompensas los
/// resuelve el servidor.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/gamificacion.dart';
import '../../navegacion/armazon.dart';
import '../../navegacion/rutas.dart';
import '../inicio/widgets/esqueletos.dart';
import '../inicio/widgets/formatos.dart';

/// Sala de trofeos.
class PantallaLogros extends StatefulWidget {
  const PantallaLogros({super.key});

  @override
  State<PantallaLogros> createState() => _PantallaLogrosState();
}

class _PantallaLogrosState extends State<PantallaLogros> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      context.read<ControladorGamificacion>().cargarLogros();
    });
  }

  Future<void> _abrirDetalle(Logro logro) {
    return mostrarHoja<void>(
      context,
      constructor: (BuildContext hoja) => _DetalleLogro(logro: logro),
    );
  }

  @override
  Widget build(BuildContext context) {
    final ControladorGamificacion gami = context.watch<ControladorGamificacion>();
    final List<Logro> logros = gami.logros;
    final bool vacioInicial = logros.isEmpty && !gami.cargandoLogros;

    return PantallaAtenea(
      titulo: 'Logros',
      mostrarVolver: true,
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        Espacio.xs,
        Espacio.md,
        Espacio.xl,
      ),
      cuerpo: RefreshIndicator(
        onRefresh: () => gami.cargarLogros(forzar: true),
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: <Widget>[
            SliverToBoxAdapter(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  _Contador(gami: gami),
                  const SizedBox(height: Espacio.sm),
                  _FiltrosDeEstado(
                    activo: gami.filtroLogros,
                    alCambiar: gami.fijarFiltroLogros,
                  ),
                  const SizedBox(height: Espacio.xs),
                  _FiltrosDeCategoria(
                    activa: gami.categoriaLogros,
                    alCambiar: gami.fijarCategoriaLogros,
                  ),
                  const SizedBox(height: Espacio.md),
                ],
              ),
            ),
            if (gami.cargandoLogros && logros.isEmpty)
              const SliverToBoxAdapter(
                child: ListaEsqueleto(filas: 4, lineas: 2),
              )
            else if (gami.errorLogros != null && logros.isEmpty)
              SliverFillRemaining(
                hasScrollBody: false,
                child: EstadoError(
                  titulo: 'La sala de trofeos está cerrada',
                  mensaje: gami.errorLogros!.mensaje,
                  alReintentar: () => gami.cargarLogros(forzar: true),
                ),
              )
            else if (vacioInicial)
              SliverFillRemaining(
                hasScrollBody: false,
                child: _SalaVacia(
                  filtro: gami.filtroLogros,
                  alVerTodos: () => gami.fijarFiltroLogros(FiltroLogros.todos),
                  alEmpezar: () => context.go(Rutas.inicio),
                ),
              )
            else
              SliverGrid.builder(
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: Medida.lecturaMax / 3,
                  mainAxisExtent: Medida.areaTactilMin * 4,
                  crossAxisSpacing: Espacio.sm,
                  mainAxisSpacing: Espacio.sm,
                ),
                itemCount: logros.length,
                itemBuilder: (BuildContext context, int i) => _Medalla(
                  logro: logros[i],
                  alTocar: () => _abrirDetalle(logros[i]),
                ),
              ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(top: Espacio.md),
                child: Center(
                  child: gami.cargandoMasLogros
                      ? const EstadoCarga()
                      : gami.hayMasLogros
                          ? TextButton(
                              onPressed: gami.masLogros,
                              child: const Text('Ver más logros'),
                            )
                          : const SizedBox.shrink(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Contador de la colección: "5 de 40 desbloqueados".
class _Contador extends StatelessWidget {
  const _Contador({required this.gami});

  final ControladorGamificacion gami;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final int total = gami.logros.length;
    final int conseguidos = gami.logrosDesbloqueados;
    final bool todos = gami.filtroLogros == FiltroLogros.todos &&
        gami.categoriaLogros == null &&
        !gami.hayMasLogros;
    final double fraccion = total == 0 ? 0 : conseguidos / total;

    return TarjetaAtenea(
      elevada: true,
      hijo: Row(
        children: <Widget>[
          Icon(Icons.military_tech_rounded, color: p.oro, size: Tipo.display),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Semantics(
                  label: todos
                      ? '$conseguidos de $total logros desbloqueados'
                      : '$total logros en esta vista, $conseguidos desbloqueados',
                  child: ExcludeSemantics(
                    child: Text(
                      todos ? '$conseguidos/$total' : '$conseguidos de $total',
                      style: Cifras.grande(context),
                    ),
                  ),
                ),
                Text(
                  todos
                      ? 'Trofeos en tu sala'
                      : 'Trofeos que cumplen este filtro',
                  style: context.textos.bodyMedium?.copyWith(
                    color: p.textoSecundario,
                  ),
                ),
                if (total > 0) ...<Widget>[
                  const SizedBox(height: Espacio.xs),
                  BarraProgreso(
                    valor: fraccion,
                    color: p.oro,
                    alto: Espacio.xs,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Todos / Desbloqueados / En progreso.
class _FiltrosDeEstado extends StatelessWidget {
  const _FiltrosDeEstado({required this.activo, required this.alCambiar});

  final FiltroLogros activo;
  final ValueChanged<FiltroLogros> alCambiar;

  @override
  Widget build(BuildContext context) {
    return SegmentedButton<FiltroLogros>(
      segments: <ButtonSegment<FiltroLogros>>[
        for (final FiltroLogros filtro in FiltroLogros.values)
          ButtonSegment<FiltroLogros>(
            value: filtro,
            label: Text(filtro.etiqueta),
          ),
      ],
      selected: <FiltroLogros>{activo},
      showSelectedIcon: false,
      onSelectionChanged: (Set<FiltroLogros> elegido) => alCambiar(elegido.first),
    );
  }
}

/// Tira horizontal de categorías.
class _FiltrosDeCategoria extends StatelessWidget {
  const _FiltrosDeCategoria({required this.activa, required this.alCambiar});

  final CategoriaLogro? activa;
  final ValueChanged<CategoriaLogro?> alCambiar;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: Medida.areaTactilMin,
      child: ListView(
        scrollDirection: Axis.horizontal,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.only(right: Espacio.xs),
            child: ChoiceChip(
              label: const Text('Todas'),
              selected: activa == null,
              onSelected: (bool _) => alCambiar(null),
            ),
          ),
          for (final CategoriaLogro categoria in CategoriaLogro.values)
            Padding(
              padding: const EdgeInsets.only(right: Espacio.xs),
              child: ChoiceChip(
                label: Text(categoria.etiqueta),
                selected: activa == categoria,
                onSelected: (bool elegida) =>
                    alCambiar(elegida ? categoria : null),
              ),
            ),
        ],
      ),
    );
  }
}

/// Una medalla de la cuadrícula.
class _Medalla extends StatelessWidget {
  const _Medalla({required this.logro, required this.alTocar});

  final Logro logro;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool conseguido = logro.estaDesbloqueado;
    final bool secreto = logro.esSecreto;
    final Color acento = colorDeNivel(logro.nivelMasAlto, p, conseguido);
    final String progreso = logro.progresoLegible;

    return TarjetaAtenea(
      alTocar: alTocar,
      padding: const EdgeInsets.all(Espacio.sm),
      colorBorde: conseguido ? acento : null,
      brillo: conseguido && !reducirMovimiento(context) ? Espacio.xs : null,
      semantica: _semantica(logro),
      hijo: ExcludeSemantics(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Center(
              child: Container(
                width: Medida.areaTactilMin + Espacio.sm,
                height: Medida.areaTactilMin + Espacio.sm,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: acento.withValues(alpha: conseguido ? 0.18 : 0.08),
                  border: Border.all(
                    color: acento.withValues(alpha: conseguido ? 0.9 : 0.35),
                    width: conseguido ? 2 : 1,
                  ),
                ),
                alignment: Alignment.center,
                child: Icon(
                  secreto
                      ? Icons.lock_outline_rounded
                      : iconoDeCategoria(logro.categoria),
                  color: acento.withValues(alpha: conseguido ? 1 : 0.6),
                  size: Tipo.titulo,
                ),
              ),
            ),
            const SizedBox(height: Espacio.xs),
            Flexible(
              child: Text(
                secreto ? 'Logro secreto' : logro.nombre,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: context.textos.titleMedium?.copyWith(
                  color: conseguido ? p.textoPrimario : p.textoSecundario,
                ),
              ),
            ),
            const SizedBox(height: Espacio.xxs),
            if (conseguido && logro.desbloqueadoEn != null)
              Text(
                fechaCorta(logro.desbloqueadoEn!),
                textAlign: TextAlign.center,
                style: context.textos.bodySmall?.copyWith(color: acento),
              )
            else if (progreso.isNotEmpty)
              Column(
                children: <Widget>[
                  BarraProgreso(
                    valor: logro.fraccion,
                    color: logro.estaCerca ? p.oro : p.arcano,
                    alto: Espacio.xs - 2,
                  ),
                  const SizedBox(height: Espacio.xxs),
                  Text(
                    logro.estaCerca ? '$progreso · casi' : progreso,
                    textAlign: TextAlign.center,
                    style: context.textos.bodySmall?.copyWith(
                      color: p.textoSecundario,
                    ),
                  ),
                ],
              )
            else
              Text(
                secreto ? 'Se revela al conseguirlo' : 'Por descubrir',
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: context.textos.bodySmall?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
          ],
        ),
      ),
    );
  }

  static String _semantica(Logro logro) {
    if (logro.esSecreto) return 'Logro secreto, todavía sin descubrir.';
    final StringBuffer texto = StringBuffer(logro.nombre);
    if (logro.estaDesbloqueado) {
      texto.write('. Desbloqueado');
      final DateTime? cuando = logro.desbloqueadoEn;
      if (cuando != null) texto.write(' el ${fechaLarga(cuando)}');
      texto.write('.');
    } else if (logro.progresoLegible.isNotEmpty) {
      texto.write('. En progreso: ${logro.progresoLegible}.');
    } else {
      texto.write('. Todavía bloqueado.');
    }
    return texto.toString();
  }
}

/// Sala sin trofeos: usuario nuevo o filtro sin resultados.
class _SalaVacia extends StatelessWidget {
  const _SalaVacia({
    required this.filtro,
    required this.alVerTodos,
    required this.alEmpezar,
  });

  final FiltroLogros filtro;
  final VoidCallback alVerTodos;
  final VoidCallback alEmpezar;

  @override
  Widget build(BuildContext context) {
    if (filtro != FiltroLogros.todos) {
      return EstadoVacio(
        icono: Icons.filter_alt_off_rounded,
        titulo: 'Nada con este filtro',
        mensaje: 'Prueba a mirar la colección completa.',
        textoAccion: 'Ver todos',
        alTocarAccion: alVerTodos,
      );
    }
    return EstadoVacio(
      icono: Icons.military_tech_outlined,
      titulo: 'Tu sala de trofeos está lista',
      mensaje:
          'El primero llega solo: completa una lección y "Primer paso" será '
          'tuyo.',
      textoAccion: 'Empezar ahora',
      alTocarAccion: alEmpezar,
    );
  }
}

/// Hoja de detalle de un logro, con sus niveles.
class _DetalleLogro extends StatelessWidget {
  const _DetalleLogro({required this.logro});

  final Logro logro;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool conseguido = logro.estaDesbloqueado;
    final Color acento = colorDeNivel(logro.nivelMasAlto, p, conseguido);

    return SafeArea(
      top: false,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(Espacio.md),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Center(
              child: Container(
                width: Espacio.xxl,
                height: Espacio.xxs,
                decoration: BoxDecoration(
                  color: p.borde,
                  borderRadius: Redondeo.rPildora,
                ),
              ),
            ),
            const SizedBox(height: Espacio.md),
            Center(
              child: Container(
                width: Medida.areaTactilMin + Espacio.lg,
                height: Medida.areaTactilMin + Espacio.lg,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: acento.withValues(alpha: conseguido ? 0.18 : 0.08),
                  border: Border.all(color: acento, width: 2),
                  boxShadow: conseguido && !reducirMovimiento(context)
                      ? Sombra.brillo(acento, Espacio.sm)
                      : null,
                ),
                alignment: Alignment.center,
                child: Icon(
                  logro.esSecreto
                      ? Icons.lock_outline_rounded
                      : iconoDeCategoria(logro.categoria),
                  color: acento,
                  size: Tipo.display,
                ),
              ),
            ),
            const SizedBox(height: Espacio.md),
            Text(
              logro.esSecreto ? 'Logro secreto' : logro.nombre,
              textAlign: TextAlign.center,
              style: context.textos.headlineSmall,
            ),
            const SizedBox(height: Espacio.xs),
            Center(
              child: Wrap(
                spacing: Espacio.xs,
                runSpacing: Espacio.xs,
                children: <Widget>[
                  Pildora(texto: logro.categoria.etiqueta),
                  if (logro.nivelMasAlto != null)
                    Pildora(
                      texto: logro.nivelMasAlto!.etiqueta,
                      icono: Icons.workspace_premium_rounded,
                      color: acento,
                    ),
                  Pildora(
                    texto: conseguido ? 'Desbloqueado' : 'En progreso',
                    icono: conseguido
                        ? Icons.check_circle_rounded
                        : Icons.hourglass_bottom_rounded,
                    color: conseguido ? p.exito : p.textoSecundario,
                  ),
                ],
              ),
            ),
            if (logro.descripcion != null) ...<Widget>[
              const SizedBox(height: Espacio.md),
              Text(
                logro.descripcion!,
                textAlign: TextAlign.center,
                style: context.textos.bodyLarge?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ],
            if (logro.progresoLegible.isNotEmpty) ...<Widget>[
              const SizedBox(height: Espacio.md),
              BarraProgreso(
                valor: logro.fraccion,
                etiqueta: 'Avance hacia el próximo nivel',
                color: acento,
                textoDerecha: logro.progresoLegible,
              ),
            ],
            if (logro.niveles.isNotEmpty) ...<Widget>[
              const SizedBox(height: Espacio.lg),
              Text('Niveles', style: context.textos.titleMedium),
              const SizedBox(height: Espacio.xs),
              for (final NivelDeLogro nivel in logro.niveles)
                _FilaNivel(nivel: nivel),
            ],
            if (conseguido && logro.desbloqueadoEn != null) ...<Widget>[
              const SizedBox(height: Espacio.md),
              FilaDato(
                icono: Icons.event_available_rounded,
                etiqueta: 'Conseguido el',
                valor: fechaLarga(logro.desbloqueadoEn!),
              ),
            ],
            const SizedBox(height: Espacio.md),
            BotonPrimario(
              texto: 'Volver a la sala',
              alTocar: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      ),
    );
  }
}

class _FilaNivel extends StatelessWidget {
  const _FilaNivel({required this.nivel});

  final NivelDeLogro nivel;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool hecho = nivel.estaDesbloqueado;
    final Color acento = colorDeNivel(nivel.nivel, p, hecho);
    final String premio = nivel.recompensa.resumen;

    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.xs),
      child: TarjetaAtenea(
        padding: const EdgeInsets.all(Espacio.sm),
        colorBorde: hecho ? acento : null,
        semantica: '${nivel.nivel.etiqueta}. Objetivo ${nivel.objetivo}. '
            '${hecho ? 'Conseguido' : 'Pendiente'}.'
            '${premio.isEmpty ? '' : ' Entrega $premio.'}',
        hijo: ExcludeSemantics(
          child: Row(
            children: <Widget>[
              Icon(
                hecho ? Icons.check_circle_rounded : Icons.circle_outlined,
                color: acento,
                size: Tipo.subtitulo,
              ),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(nivel.nivel.etiqueta, style: context.textos.titleMedium),
                    if (nivel.objetivo > 0)
                      Text(
                        'Objetivo: ${nivel.objetivo}',
                        style: context.textos.bodySmall?.copyWith(
                          color: p.textoSecundario,
                        ),
                      ),
                  ],
                ),
              ),
              if (premio.isNotEmpty)
                Pildora(texto: premio, icono: Medallon.xp.icono, color: p.oro),
            ],
          ),
        ),
      ),
    );
  }
}

/// Color de la medalla según su nivel; apagado mientras está bloqueada.
Color colorDeNivel(NivelLogro? nivel, AteneaPalette p, bool conseguido) {
  if (!conseguido) return p.textoSecundario;
  return switch (nivel) {
    NivelLogro.bronce => p.brasa,
    NivelLogro.plata => p.dominio,
    NivelLogro.oro => p.oro,
    NivelLogro.unico => p.arcano,
    null => p.oro,
  };
}

/// Emblema de cada categoría de la sala de trofeos.
IconData iconoDeCategoria(CategoriaLogro categoria) => switch (categoria) {
      CategoriaLogro.aprendizaje => Icons.school_rounded,
      CategoriaLogro.dominio => Icons.psychology_rounded,
      CategoriaLogro.constancia => Icons.local_fire_department_rounded,
      CategoriaLogro.coleccion => Icons.inventory_2_rounded,
      CategoriaLogro.exploracion => Icons.explore_rounded,
      CategoriaLogro.hito => Icons.flag_rounded,
    };
